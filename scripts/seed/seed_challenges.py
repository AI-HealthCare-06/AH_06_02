"""챌린지 마스터 시드. docs/01_planning/challenge-master.csv 를 challenges 테이블에 넣는다.

    uv run python -m scripts.seed.seed_challenges [--csv PATH] [--allow-missing]

code 기준 upsert 라 다시 돌려도 행이 늘지 않는다.
CSV 빈 칸은 임의 값으로 채우지 않는다. NULL 허용 컬럼은 None, NOT NULL 컬럼은 모델·DB 기본값에 맡긴다.
read_csv · parse_rows · upsert_by_code 는 seed_monsters · seed_rewards 도 같이 쓴다.
"""

import argparse
import asyncio
import csv
import json
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from tortoise import Tortoise, fields, models
from tortoise.transactions import in_transaction

from app.models.challenges import Challenge

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = REPO_ROOT / "docs" / "01_planning" / "challenge-master.csv"

#: 운영 값이 정해지지 않으면 시드를 거부하는 컬럼.
#: reward_xp 가 기본값 0으로 들어가면 REQ-RECO-003 의 레벨 체계가 동작하지 않는다.
OPERATIONAL_COLUMNS = ("reward_xp", "manual_fallback_allowed")

BOOLEAN_VALUES = {"true": True, "false": False}


class SeedError(ValueError):
    pass


@dataclass
class SeedResult:
    created: int
    updated: int


def read_csv(path: Path) -> list[dict[str, str]]:
    # 시트에서 내려받은 CSV 는 UTF-8 BOM 으로 시작한다. utf-8 로 열면 첫 헤더가 '﻿code' 가 되어 code 를 못 찾는다
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def missing_operational_values(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """운영 값 컬럼별로 비어 있는 행의 code 를 모은다."""
    missing: dict[str, list[str]] = {}
    for column in OPERATIONAL_COLUMNS:
        codes = [row["code"] for row in rows if not (row.get(column) or "").strip()]
        if codes:
            missing[column] = codes
    return missing


def _convert(field: fields.Field[Any], column: str, raw: str) -> Any:
    enum_type = getattr(field, "enum_type", None)
    try:
        if enum_type is not None:
            return enum_type(raw)
        if isinstance(field, fields.BooleanField):
            return BOOLEAN_VALUES[raw.lower()]
        if isinstance(field, fields.DecimalField):
            return Decimal(raw)
        if isinstance(field, fields.IntField | fields.SmallIntField | fields.BigIntField):
            return int(raw)
        if isinstance(field, fields.JSONField):
            return json.loads(raw)
    except (KeyError, ValueError, InvalidOperation) as exc:
        raise SeedError(f"{column} 값 {raw!r} 을 해석할 수 없습니다.") from exc
    return raw


def parse_rows(rows: list[dict[str, str]], model: type[models.Model] = Challenge) -> list[dict[str, Any]]:
    """CSV 행을 모델 필드 값으로 바꾼다. DB 에 쓰기 전에 전 행을 먼저 검사한다."""
    fields_map = model._meta.fields_map
    if rows:
        unknown = set(rows[0]) - set(fields_map)
        if unknown:
            raise SeedError(f"{model._meta.db_table} 에 없는 컬럼입니다: {sorted(unknown)}")

    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        values: dict[str, Any] = {}
        for column, raw in row.items():
            field = fields_map[column]
            text = (raw or "").strip()
            if text:
                values[column] = _convert(field, column, text)
            elif field.null:
                values[column] = None
            elif field.default is None:
                raise SeedError(f"{line}행 {column} 은 필수입니다.")
            # NOT NULL 이고 기본값이 있는 컬럼은 빼서 모델·DB 기본값에 맡긴다

        code = str(values["code"])
        if code in seen:
            raise SeedError(f"{line}행 code {code} 가 중복입니다.")
        seen.add(code)
        parsed.append(values)
    return parsed


async def upsert_challenges(parsed: list[dict[str, Any]]) -> SeedResult:
    return await upsert_by_code(Challenge, parsed)


async def upsert_by_code(model: type[models.Model], parsed: list[dict[str, Any]]) -> SeedResult:
    """code 기준 upsert. 한 트랜잭션으로 묶어 중간에 실패하면 아무것도 남기지 않는다."""
    created = updated = 0
    async with in_transaction():
        for values in parsed:
            defaults = {key: value for key, value in values.items() if key != "code"}
            _, was_created = await model.update_or_create(code=values["code"], defaults=defaults)
            if was_created:
                created += 1
            else:
                updated += 1
    return SeedResult(created=created, updated=updated)


def check_operational_values(rows: list[dict[str, str]], *, allow_missing: bool) -> bool:
    """운영 값이 비어 있으면 알리고, 플래그 없이는 진행하지 않는다. 진행 가능하면 True."""
    missing = missing_operational_values(rows)
    if not missing:
        return True
    for column, codes in missing.items():
        print(f"운영 값 미정: {column} 가 {len(codes)}행 비어 있습니다 ({', '.join(codes)})")
    if not allow_missing:
        print("시드를 중단합니다. 운영 값을 채우거나, 기본값으로 넣으려면 --allow-missing 을 붙이세요.")
        return False
    print("--allow-missing: 빈 칸은 DB 기본값으로 들어갑니다.")
    return True


async def run(csv_path: Path, *, allow_missing: bool) -> int:
    rows = read_csv(csv_path)
    if not check_operational_values(rows, allow_missing=allow_missing):
        return 1
    parsed = parse_rows(rows)

    from app.core.db.databases import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await upsert_challenges(parsed)
        total = await Challenge.all().count()
    finally:
        await Tortoise.close_connections()
    print(f"challenges: 생성 {result.created} · 갱신 {result.updated} · 테이블 전체 {total}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="챌린지 마스터 CSV 를 challenges 에 upsert 한다")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--allow-missing", action="store_true", help="운영 값이 비어 있어도 DB 기본값으로 넣는다")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(args.csv, allow_missing=args.allow_missing)))
    except SeedError as exc:
        print(f"시드 실패: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
