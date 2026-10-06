"""캐릭터 마스터 시드. docs/01_planning/monster-master.csv 를 monsters 테이블에 넣는다.

    uv run python -m scripts.seed.seed_monsters [--csv PATH]

code 기준 upsert 라 다시 돌려도 행이 늘지 않는다. 구조는 seed_challenges.py 와 같다.
CSV 의 factor_keys 가 ai_worker/model_contract.py 의 MONSTER_FACTORS 와 다르면 DB 에 쓰지 않는다.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from tortoise import Tortoise

from ai_worker.model_contract import MONSTER_FACTORS
from app.models.challenges import Monster
from scripts.seed.seed_challenges import REPO_ROOT, SeedError, SeedResult, parse_rows, read_csv, upsert_by_code

DEFAULT_CSV = REPO_ROOT / "docs" / "01_planning" / "monster-master.csv"


def check_monster_factors(parsed: list[dict[str, Any]]) -> None:
    """factor_keys 가 MONSTER_FACTORS 와 같은지 본다. 순서는 의미가 없어 집합으로 비교한다.

    MONSTER_FACTORS 에 없는 캐릭터는 SHAP 요인이 없어야 한다. 스파이크는 실측 혈당으로 위협도를 내므로 [] 가 정상이다.
    MONSTER_FACTORS 에만 있고 CSV 에 없는 캐릭터는 이번 마스터 범위 밖이라 오류로 보지 않는다.
    """
    mismatched = []
    for values in parsed:
        code = values["code"]
        keys = list(values.get("factor_keys") or [])
        expected = set(MONSTER_FACTORS.get(code, ()))
        if len(keys) != len(set(keys)) or set(keys) != expected:
            mismatched.append(f"{code}: CSV {sorted(keys)} · 코드 {sorted(expected)}")
    if mismatched:
        raise SeedError("factor_keys 가 MONSTER_FACTORS 와 다릅니다. " + " / ".join(mismatched))


async def seed_monsters(rows: list[dict[str, str]]) -> SeedResult:
    """검증을 모두 통과해야 쓴다. 실패하면 아무 행도 남기지 않는다."""
    parsed = parse_rows(rows, Monster)
    check_monster_factors(parsed)
    return await upsert_by_code(Monster, parsed)


async def run(csv_path: Path) -> int:
    rows = read_csv(csv_path)
    # DB 연결 전에 먼저 검사해 어긋나면 연결조차 하지 않는다
    check_monster_factors(parse_rows(rows, Monster))

    from app.core.db.databases import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await seed_monsters(rows)
        total = await Monster.all().count()
    finally:
        await Tortoise.close_connections()
    print(f"monsters: 생성 {result.created} · 갱신 {result.updated} · 테이블 전체 {total}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="캐릭터 마스터 CSV 를 monsters 에 upsert 한다")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(args.csv)))
    except SeedError as exc:
        print(f"시드 실패: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
