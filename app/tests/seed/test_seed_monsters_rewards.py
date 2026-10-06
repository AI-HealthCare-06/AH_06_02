import csv
import subprocess
import sys
from pathlib import Path

import pytest
from tortoise.contrib.test import TestCase

from app.models.challenges import Monster, Reward
from scripts.seed.seed_challenges import DEFAULT_CSV as CHALLENGE_CSV
from scripts.seed.seed_challenges import REPO_ROOT, SeedError, read_csv, upsert_challenges
from scripts.seed.seed_challenges import parse_rows as parse_challenge_rows
from scripts.seed.seed_monsters import DEFAULT_CSV as MONSTER_CSV
from scripts.seed.seed_monsters import seed_monsters
from scripts.seed.seed_rewards import DEFAULT_CSV as REWARD_CSV
from scripts.seed.seed_rewards import seed_rewards


def _bad_monster_rows() -> list[dict[str, str]]:
    rows = read_csv(MONSTER_CSV)
    return [{**row, "factor_keys": '["smoking_current"]'} if row["code"] == "spike" else row for row in rows]


def test_bom_does_not_break_code_column() -> None:
    for path in (MONSTER_CSV, REWARD_CSV):
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")
        assert "code" in read_csv(path)[0]


def test_factor_mismatch_exits_with_code_1_before_touching_the_db(tmp_path: Path) -> None:
    rows = _bad_monster_rows()
    path = tmp_path / "monster.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    result = subprocess.run(
        [sys.executable, "-m", "scripts.seed.seed_monsters", "--csv", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "MONSTER_FACTORS" in result.stdout


class TestSeedMonsters(TestCase):
    async def test_four_rows_and_idempotent(self) -> None:
        first = await seed_monsters(read_csv(MONSTER_CSV))
        second = await seed_monsters(read_csv(MONSTER_CSV))

        assert (first.created, second.created, second.updated) == (4, 0, 4)
        assert await Monster.all().count() == 4

    async def test_spike_keeps_empty_factor_keys(self) -> None:
        await seed_monsters(read_csv(MONSTER_CSV))

        spike = await Monster.get(code="spike")
        assert spike.factor_keys == []

    async def test_factor_mismatch_leaves_zero_rows(self) -> None:
        with pytest.raises(SeedError):
            await seed_monsters(_bad_monster_rows())

        assert await Monster.all().count() == 0


class TestSeedRewards(TestCase):
    async def _seed_challenges(self) -> None:
        await upsert_challenges(parse_challenge_rows(read_csv(CHALLENGE_CSV)))

    async def test_one_row_and_idempotent(self) -> None:
        await self._seed_challenges()
        await seed_rewards(read_csv(REWARD_CSV))
        await seed_rewards(read_csv(REWARD_CSV))

        assert await Reward.all().count() == 1

    async def test_required_level_is_null(self) -> None:
        await self._seed_challenges()
        await seed_rewards(read_csv(REWARD_CSV))

        blade = await Reward.get(code="gluco_blade")
        # 1단계는 레벨업 보상이 범위 밖이라 빈 칸을 NULL 로 넣는다
        assert blade.required_level is None
        assert blade.linked_challenge_code == "CH_WALK_AFTER_MEAL"

    async def test_unknown_linked_challenge_leaves_zero_rows(self) -> None:
        # 챌린지 시드 전이라 CH_WALK_AFTER_MEAL 이 없다
        with pytest.raises(SeedError):
            await seed_rewards(read_csv(REWARD_CSV))

        assert await Reward.all().count() == 0
