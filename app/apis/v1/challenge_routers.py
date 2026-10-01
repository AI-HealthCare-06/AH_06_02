from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_request_user
from app.dtos.challenges import ChallengeStartRequest, ChallengeStopRequest
from app.dtos.envelope import ok
from app.models.challenges import UserChallenge, UserChallengeStatus
from app.models.users import User
from app.services.challenges import ChallengeCoreService

challenge_router = APIRouter(tags=["challenges"])


@challenge_router.post("/user-challenges", status_code=status.HTTP_201_CREATED)
async def start_user_challenges(
    request: ChallengeStartRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeCoreService, Depends(ChallengeCoreService)],
) -> dict[str, Any]:
    created = await service.start_from_recommendations(
        user_id=user.id,
        recommendation_ids=request.recommendation_ids,
        safety_confirmed=request.safety_confirmed,
    )
    active_count = await UserChallenge.filter(
        user_id=user.id,
        status=UserChallengeStatus.ACTIVE,
    ).count()
    items = [
        {
            "user_challenge_id": item.id,
            "challenge_id": item.challenge_id,
            "status": str(item.status),
            "start_date": item.start_date,
            "end_date": item.end_date,
            "daily_target_count": item.daily_target_count_snapshot,
            "target_value": float(item.target_value_snapshot) if item.target_value_snapshot is not None else None,
            "duration_days": item.duration_days_snapshot,
        }
        for item in created
    ]
    return ok({"items": items, "active_count": active_count})


@challenge_router.post(
    "/user-challenges/{user_challenge_id}/stop",
    status_code=status.HTTP_200_OK,
)
async def stop_user_challenge(
    user_challenge_id: int,
    request: ChallengeStopRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeCoreService, Depends(ChallengeCoreService)],
) -> dict[str, Any]:
    item = await service.stop(
        user_id=user.id,
        user_challenge_id=user_challenge_id,
        stop_reason=request.stop_reason,
    )
    return ok(
        {
            "user_challenge_id": item.id,
            "status": str(item.status),
            "stopped_at": item.stopped_at,
            "stop_reason": item.stop_reason,
        }
    )
