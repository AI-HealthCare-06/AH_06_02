from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.core.errors import AppError, ErrorCode
from app.dependencies.security import get_request_user
from app.dtos.challenges import (
    ChallengeLogRequest,
    ChallengeStartRequest,
    ChallengeStopRequest,
    RecommendationActionRequest,
)
from app.dtos.envelope import ok
from app.models.challenges import (
    ChallengeLog,
    CooldownChoice,
    RecommendationAction,
    Reward,
    UserChallenge,
    UserChallengeStatus,
)
from app.models.users import User
from app.services.challenges import ChallengeCoreService
from app.services.monsters import MonsterService
from app.services.recommendations import RecommendationService, target_monster_body

challenge_router = APIRouter(tags=["challenges"])


def get_recommendation_service() -> RecommendationService:
    return RecommendationService()


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


@challenge_router.post("/challenge-recommendations/generate", status_code=status.HTTP_200_OK)
async def generate_recommendations(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> dict[str, Any]:
    """CHLG-01 추천 생성."""
    result = await service.generate(user)
    target = target_monster_body(result.monster)
    items = [
        {
            "recommendation_id": item.id,
            "challenge_id": item.challenge_id,
            "title": result.challenges[item.challenge_id].title,
            "factor_key": item.factor_key,
            "factor_score": _float(item.factor_score),
            "rank": item.rank,
            "difficulty": result.challenges[item.challenge_id].difficulty,
            "verification_type": result.challenges[item.challenge_id].verification_type,
            "context_label": result.challenges[item.challenge_id].context_label,
            "cycle_id": item.cycle_id,
            "target_monster": target,
        }
        for item in result.items
    ]
    # 어느 모델 기준 점수인지 추적한다. challenge_recommendations 에는 저장할 컬럼이 없다
    return ok({"items": items, "total": len(items), "model_version": result.model_version})


@challenge_router.get("/challenge-recommendations", status_code=status.HTTP_200_OK)
async def list_recommendations(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """CHLG-02 추천 카드 조회."""
    items, total = await service.list_cards(user, page, size)
    return ok({"items": items, "total": total, "page": page, "size": size})


@challenge_router.patch("/challenge-recommendations/{recommendation_id}", status_code=status.HTTP_200_OK)
async def act_on_recommendation(
    recommendation_id: int,
    request: RecommendationActionRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> dict[str, Any]:
    """CHLG-03 추천 거절·해당없음/쿨다운 설정."""
    try:
        cooldown = CooldownChoice(request.cooldown_choice) if request.cooldown_choice is not None else None
    except ValueError as exc:
        raise AppError(ErrorCode.CHLG_INVALID_COOLDOWN) from exc
    row = await service.act(user, recommendation_id, RecommendationAction(request.action), cooldown)
    return ok(
        {
            "recommendation_id": row.id,
            "action": row.action,
            "consecutive_reject_count": row.consecutive_reject_count,
            "cooldown_choice": row.cooldown_choice,
            "exclude_until": row.exclude_until,
            "suppressed_until_manual": row.suppressed_until_manual,
        }
    )


@challenge_router.patch("/challenge-recommendations/{recommendation_id}/unsuppress", status_code=status.HTTP_200_OK)
async def unsuppress_recommendation(
    recommendation_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> dict[str, Any]:
    """CHLG-04 수동 제외 해제."""
    row = await service.unsuppress(user, recommendation_id)
    return ok({"recommendation_id": row.id, "suppressed_until_manual": row.suppressed_until_manual})


@challenge_router.post("/user-challenges", status_code=status.HTTP_201_CREATED)
async def start_user_challenges(
    request: ChallengeStartRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeCoreService, Depends(ChallengeCoreService)],
) -> dict[str, Any]:
    """CHLG-05 챌린지 시작."""
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
            "cycle_id": item.cycle_id,
            "status": str(item.status),
            "start_date": item.start_date,
            "end_date": item.end_date,
            "daily_target_count": item.daily_target_count_snapshot,
            "target_value": _float(item.target_value_snapshot),
            "duration_days": item.duration_days_snapshot,
            "goal_config_snapshot": item.goal_config_snapshot,
        }
        for item in created
    ]
    return ok({"items": items, "active_count": active_count})


@challenge_router.get("/user-challenges", status_code=status.HTTP_200_OK)
async def list_user_challenges(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeCoreService, Depends(ChallengeCoreService)],
    status_: Annotated[UserChallengeStatus, Query(alias="status")] = UserChallengeStatus.ACTIVE,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """CHLG-06 진행 중 챌린지 조회."""
    items, total = await service.list_user_challenges(user_id=user.id, status=status_, page=page, size=size)
    return ok({"items": items, "total": total, "page": page, "size": size})


@challenge_router.post("/user-challenges/{user_challenge_id}/logs", status_code=status.HTTP_201_CREATED)
async def record_challenge_log(
    user_challenge_id: int,
    request: ChallengeLogRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeCoreService, Depends(ChallengeCoreService)],
) -> dict[str, Any]:
    """CHLG-07 챌린지 수행 기록."""
    result = await service.record_log(
        user_id=user.id,
        user_challenge_id=user_challenge_id,
        occurred_at=request.occurred_at,
        context_slot=request.context_slot,
        value=request.value,
        verification_method=request.verification_method,
        evidence_url=request.evidence_url,
    )
    return ok(
        {
            "log_id": result.log.id,
            "result": result.log.result,
            "verification_status": result.log.verification_status,
            "reward_eligible": result.log.reward_eligible,
            "xp_granted": result.log.xp_granted,
            "weekly_progress": result.weekly_progress,
            "level_up": result.level_up,
            "new_level": result.new_level,
            # 이번 기록으로 새로 받은 보상만 싣는다. 이미 가졌거나 지급하지 않았으면 null
            "reward": _reward_body(result.reward) if result.reward else None,
        }
    )


def _reward_body(reward: Reward) -> dict[str, Any]:
    """획득 안내에 필요한 최소한. 이름은 문구, 종류는 표현 방식, code 는 화면 자산 키, id 는 RWRD-01 과 연결한다."""
    return {"reward_id": reward.id, "code": reward.code, "name": reward.name, "reward_kind": reward.reward_kind}


def _log_body(log: ChallengeLog) -> dict[str, Any]:
    return {
        "log_id": log.id,
        "log_date": log.log_date,
        "occurred_at": log.occurred_at,
        "sequence_no": log.sequence_no,
        "context_slot": log.context_slot,
        "value": _float(log.value),
        "unit": log.unit,
        "result": log.result,
        "verification_method": log.verification_method,
        "verification_status": log.verification_status,
        "reward_eligible": log.reward_eligible,
        "xp_granted": log.xp_granted,
    }


@challenge_router.get("/user-challenges/{user_challenge_id}/logs", status_code=status.HTTP_200_OK)
async def list_challenge_logs(
    user_challenge_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[ChallengeCoreService, Depends(ChallengeCoreService)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """CHLG-08 수행 기록 조회."""
    logs, total = await service.list_logs(
        user_id=user.id,
        user_challenge_id=user_challenge_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        size=size,
    )
    return ok({"items": [_log_body(log) for log in logs], "total": total, "page": page, "size": size})


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
    """CHLG-09 챌린지 중단."""
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


@challenge_router.get("/monsters/me", status_code=status.HTTP_200_OK)
async def my_monsters(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MonsterService, Depends(MonsterService)],
) -> dict[str, Any]:
    """MNSTR-01 내 위험요인 도감 조회."""
    return ok({"items": await service.list_mine(user.id)})
