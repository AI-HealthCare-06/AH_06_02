"""임시 테스트 도구. 질의 챗봇을 주기 제한 없이 시험하려고 둔다.

질의 챗봇은 슬롯이 남아 있을 때만, 즉 28일 주기가 끝나고 다음 추천을 열 때 쓸 수 있다.
테스트 계정이 그때까지 기다리지 않도록 주기 종료를 앞당긴다.
TEST_TOOL_EMAILS 에 적은 계정만 쓰고, 나머지 계정에는 경로가 없는 것처럼 404 를 준다.
테스트가 끝나면 이 파일, v1 등록 한 줄, 설정 TEST_TOOL_EMAILS, frontend/test-tools/ 를 함께 지운다.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.dependencies.security import get_request_user
from app.dtos.envelope import ok
from app.models.challenges import UserChallenge, UserChallengeStatus
from app.models.users import User
from app.services.attack_cycles import AttackCycleService, lock_user, today_kst

test_tool_router = APIRouter(prefix="/test-tools", tags=["test-tools"], include_in_schema=False)


def allowed_test_user(user: Annotated[User, Depends(get_request_user)]) -> User:
    emails = {email.strip().casefold() for email in config.TEST_TOOL_EMAILS.split(",") if email.strip()}
    if user.email.casefold() not in emails:
        raise AppError(ErrorCode.NOT_FOUND)
    return user


async def cycle_body(service: AttackCycleService, user: User) -> dict[str, Any]:
    today = today_kst(datetime.now(config.TIMEZONE))
    cycle = await service.get_current(user.id)
    active = UserChallenge.filter(user_id=user.id, status=UserChallengeStatus.ACTIVE)
    if cycle is None:
        return {"cycle": None, "active_challenges": await active.count(), "remaining_slots": None}
    return {
        "cycle": {
            "cycle_id": cycle.id,
            "status": cycle.status,
            "start_date": cycle.start_date,
            "end_date": cycle.end_date,
        },
        "active_challenges": await active.count(),
        "remaining_slots": service.remaining_slots(
            cycle, await active.filter(cycle_id=cycle.id).count(), await active.count(), today
        ),
    }


@test_tool_router.get("/attack-cycle", status_code=status.HTTP_200_OK)
async def read_attack_cycle(user: Annotated[User, Depends(allowed_test_user)]) -> dict[str, Any]:
    """테스트 계정의 지금 주기와 남은 슬롯."""
    return ok(await cycle_body(AttackCycleService(), user))


@test_tool_router.post("/attack-cycle/finish", status_code=status.HTTP_200_OK)
async def finish_attack_cycle(user: Annotated[User, Depends(allowed_test_user)]) -> dict[str, Any]:
    """진행 중 주기의 마지막 날을 어제로 당기고 실제 종료 처리(close_expired)로 닫는다.

    진행 중 미션은 28일이 지난 것과 똑같이 '기간 종료'가 되고, 다음 추천이 새 주기를 연다.
    """
    service = AttackCycleService()
    now = datetime.now(config.TIMEZONE)
    today = today_kst(now)
    async with in_transaction():
        await lock_user(user.id)
        cycle = await service.get_active(user.id)
        if cycle is None:
            return ok({"finished": False, "closed_cycle_id": None, **await cycle_body(service, user)})
        ended = await UserChallenge.filter(cycle_id=cycle.id, status=UserChallengeStatus.ACTIVE).count()
        cycle.end_date = today - timedelta(days=1)
        await cycle.save(update_fields=["end_date", "updated_at"])
    await service.close_expired(user.id, today, now)
    return ok(
        {"finished": True, "closed_cycle_id": cycle.id, "ended_challenges": ended, **await cycle_body(service, user)}
    )
