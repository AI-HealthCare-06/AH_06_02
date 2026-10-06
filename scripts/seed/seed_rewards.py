"""보상 마스터 시드. docs/01_planning/reward-master.csv 를 rewards 테이블에 넣는다.

    uv run python -m scripts.seed.seed_rewards [--csv PATH]

code 기준 upsert 라 다시 돌려도 행이 늘지 않는다. 구조는 seed_challenges.py 와 같다.
linked_challenge_code 는 challenges 에 실제로 있어야 한다. 챌린지 시드를 먼저 돌린다.
required_level 빈 칸은 NULL 이다. 1단계는 레벨업 보상을 범위 밖으로 두기로 A·D 가 합의했다.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from tortoise import Tortoise

from app.models.challenges import Challenge, Reward
from scripts.seed.seed_challenges import REPO_ROOT, SeedError, SeedResult, parse_rows, read_csv, upsert_by_code

DEFAULT_CSV = REPO_ROOT / "docs" / "01_planning" / "reward-master.csv"


async def check_linked_challenges(parsed: list[dict[str, Any]]) -> None:
    """linked_challenge_code 가 challenges 에 있는 code 인지 본다."""
    linked = {values["linked_challenge_code"] for values in parsed if values.get("linked_challenge_code")}
    existing = set(await Challenge.filter(code__in=list(linked)).values_list("code", flat=True))
    missing = sorted(str(code) for code in linked - existing)
    if missing:
        raise SeedError(f"challenges 에 없는 linked_challenge_code 입니다: {missing}")


async def seed_rewards(rows: list[dict[str, str]]) -> SeedResult:
    """검증을 모두 통과해야 쓴다. 실패하면 아무 행도 남기지 않는다."""
    parsed = parse_rows(rows, Reward)
    await check_linked_challenges(parsed)
    return await upsert_by_code(Reward, parsed)


async def run(csv_path: Path) -> int:
    rows = read_csv(csv_path)
    parse_rows(rows, Reward)

    from app.core.db.databases import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await seed_rewards(rows)
        total = await Reward.all().count()
    finally:
        await Tortoise.close_connections()
    print(f"rewards: 생성 {result.created} · 갱신 {result.updated} · 테이블 전체 {total}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="보상 마스터 CSV 를 rewards 에 upsert 한다")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(args.csv)))
    except SeedError as exc:
        print(f"시드 실패: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
