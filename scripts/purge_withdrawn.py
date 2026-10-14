"""탈퇴 +30일이 지난 계정의 식별정보를 지운다 (REQ-USER-009).

    uv run python -m scripts.purge_withdrawn [--dry-run] [--now 2026-11-05T03:00]

하루 한 번 서버 crontab 에서 부르는 것을 전제로 한다. 앱 안에 스케줄러를 두지 않아
컨테이너가 여러 대여도 중복 실행이 데이터를 망가뜨리지 않는다. 이미 지운 계정은
다시 고르지 않으므로 여러 번 돌려도 결과가 같다.

지우는 것은 users 의 email·nickname·password_hash 와 challenge_recommendations 의
conversation_snapshot 이다 (REQ-USER-009 · REQ-CHLG-012). 행은 남기고 건강기록과
예측 결과도 지우지 않는다. 챌린지 인증 사진은 업로드(HLTH-03)가 아직 없어 범위 밖이다.
"""

import argparse
import asyncio
import sys
from datetime import datetime

from tortoise import Tortoise

from app.core import config
from app.services.retention import RetentionService


def parse_now(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=config.TIMEZONE)


async def run(now: datetime | None, dry_run: bool) -> int:
    from app.core.db.databases import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await RetentionService().purge_withdrawn(now=now, dry_run=dry_run)
    finally:
        await Tortoise.close_connections()
    label = "대상" if dry_run else "파기"
    print(f"탈퇴 계정 식별정보 {label} {result.count}건")
    # id 는 개인정보가 아니라 로그에 남겨도 된다. 되짚을 때 쓴다
    if result.count:
        print("user_id:", ", ".join(str(user_id) for user_id in result.purged_user_ids))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="대상만 세고 쓰지 않는다")
    parser.add_argument("--now", help="기준 시각 ISO 8601. 생략하면 현재 KST")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(parse_now(args.now), args.dry_run)))


if __name__ == "__main__":
    main()
