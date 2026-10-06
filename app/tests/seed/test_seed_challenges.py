from pathlib import Path

import pytest
from tortoise.contrib.test import TestCase

from app.models.challenges import Challenge, ContextType
from scripts.seed.seed_challenges import (
    DEFAULT_CSV,
    SeedError,
    check_operational_values,
    missing_operational_values,
    parse_rows,
    read_csv,
    upsert_challenges,
)

CSV_ROWS = 19


def test_bom_does_not_break_code_column() -> None:
    rows = read_csv(DEFAULT_CSV)

    assert DEFAULT_CSV.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "code" in rows[0]
    assert "﻿code" not in rows[0]
    assert rows[0]["code"] == "CH_WALK_AFTER_MEAL"


def test_csv_has_19_rows_with_unique_codes() -> None:
    rows = read_csv(DEFAULT_CSV)

    assert len(rows) == CSV_ROWS
    assert len({row["code"] for row in rows}) == CSV_ROWS


def test_missing_operational_values_are_refused_without_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rows = read_csv(DEFAULT_CSV)

    missing = missing_operational_values(rows)
    assert len(missing["reward_xp"]) == CSV_ROWS
    assert len(missing["manual_fallback_allowed"]) == CSV_ROWS
    assert check_operational_values(rows, allow_missing=False) is False
    assert "운영 값 미정" in capsys.readouterr().out
    assert check_operational_values(rows, allow_missing=True) is True


def test_blank_cells_are_not_filled_with_invented_values() -> None:
    parsed = parse_rows(read_csv(DEFAULT_CSV))

    first = parsed[0]
    # NULL 허용 컬럼은 None
    assert first["description"] is None
    assert first["personalization_policy"] is None
    # NOT NULL 컬럼은 값을 넣지 않고 기본값에 맡긴다
    assert "reward_xp" not in first
    assert "manual_fallback_allowed" not in first


def test_unknown_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("code,title,category,goal_type,hp\nCH_X,x,diet,boolean,1\n", encoding="utf-8")

    with pytest.raises(SeedError):
        parse_rows(read_csv(path))


class TestUpsertChallenges(TestCase):
    async def test_all_19_rows_are_inserted(self) -> None:
        result = await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))

        assert result.created == CSV_ROWS
        assert await Challenge.all().count() == CSV_ROWS
        walk = await Challenge.get(code="CH_WALK_AFTER_MEAL")
        assert walk.context_type == ContextType.MEAL
        assert walk.context_slots == ["lunch", "dinner"]
        assert walk.daily_target_count == 2

    async def test_running_twice_keeps_19_rows(self) -> None:
        parsed = parse_rows(read_csv(DEFAULT_CSV))
        await upsert_challenges(parsed)
        second = await upsert_challenges(parsed)

        assert second.created == 0
        assert second.updated == CSV_ROWS
        assert await Challenge.all().count() == CSV_ROWS

    async def test_inactive_rows_follow_the_factor_map(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))

        # challenge-factor-map.md 'v0 활성' False 두 행
        disabled = await Challenge.filter(is_enabled=False).values_list("code", flat=True)
        assert sorted(disabled) == ["CH_SLOW_EAT_20", "CH_VEGGIE_FIRST"]

    async def test_blank_not_null_columns_take_db_defaults(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))

        walk = await Challenge.get(code="CH_WALK_AFTER_MEAL")
        assert walk.reward_xp == 0
        assert walk.manual_fallback_allowed is True
        assert walk.description is None
