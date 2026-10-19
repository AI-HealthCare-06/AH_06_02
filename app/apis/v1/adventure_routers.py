"""v5 타이머·보상·꾸미기·성장 기록 확장 API."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.dependencies.security import get_request_user
from app.dtos.adventure import AdventurerUpdateRequest, RewardClaimRequest, TimerStartRequest
from app.dtos.envelope import ok
from app.models.challenges import RewardDraw
from app.models.users import User
from app.services.adventure_progress import AdventureProgressService
from app.services.adventure_rewards import AdventureRewardService, draw_body, state_body
from app.services.challenge_timers import ChallengeTimerService

adventure_router = APIRouter(tags=["adventure"])


@adventure_router.get("/adventure/progress")
async def progress(user: Annotated[User, Depends(get_request_user)], month: str | None = None) -> dict[str, Any]:
    return ok(await AdventureProgressService().get(user.id, month))


@adventure_router.post("/user-challenges/{user_challenge_id}/timers")
async def start_timer(
    user_challenge_id: int, request: TimerStartRequest, user: Annotated[User, Depends(get_request_user)]
) -> dict[str, Any]:
    return ok(await ChallengeTimerService().start(user.id, user_challenge_id, request.context_slot))


@adventure_router.get("/user-challenges/{user_challenge_id}/timers/{timer_session_id}")
async def get_timer(
    user_challenge_id: int, timer_session_id: int, user: Annotated[User, Depends(get_request_user)]
) -> dict[str, Any]:
    return ok(await ChallengeTimerService().get(user.id, user_challenge_id, timer_session_id))


@adventure_router.get("/rewards/catalog")
async def catalog(user: Annotated[User, Depends(get_request_user)]) -> dict[str, Any]:
    return ok(await AdventureRewardService().catalog(user.id))


@adventure_router.get("/reward-draws")
async def draws(
    user: Annotated[User, Depends(get_request_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    query = RewardDraw.filter(user_id=user.id)
    items = await query.order_by("-id").offset((page - 1) * size).limit(size)
    return ok({"items": [draw_body(draw) for draw in items], "total": await query.count(), "page": page, "size": size})


@adventure_router.post("/reward-draws/{draw_id}/claim")
async def claim(
    draw_id: int, request: RewardClaimRequest, user: Annotated[User, Depends(get_request_user)]
) -> dict[str, Any]:
    return ok(await AdventureRewardService().claim(user.id, draw_id, request.positions))


@adventure_router.get("/adventurer/me")
async def adventurer(user: Annotated[User, Depends(get_request_user)]) -> dict[str, Any]:
    return ok(state_body(await AdventureRewardService().state(user.id)))


@adventure_router.patch("/adventurer/me")
async def update_adventurer(
    request: AdventurerUpdateRequest, user: Annotated[User, Depends(get_request_user)]
) -> dict[str, Any]:
    return ok(await AdventureRewardService().update(user.id, request.equipment, request.room))


@adventure_router.post("/adventurer/me/upgrade")
async def upgrade(user: Annotated[User, Depends(get_request_user)]) -> dict[str, Any]:
    return ok(await AdventureRewardService().upgrade(user.id))
