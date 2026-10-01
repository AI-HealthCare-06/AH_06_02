from datetime import date, datetime, timedelta

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    Challenge,
    ChallengeRecommendation,
    Monster,
    RecommendationAction,
    UserChallenge,
    UserChallengeStatus,
    UserMonster,
)

MAX_ACTIVE_CHALLENGES = 3


def week_start_for(value: date | datetime) -> date:
    """월요일 00:00 KST 기준 달력 주간의 시작일을 반환한다."""
    current = value.astimezone(config.TIMEZONE).date() if isinstance(value, datetime) else value
    return current - timedelta(days=current.weekday())


def progress_rate(completed_count: int, daily_target_count: int) -> float:
    """일일 목표 대비 진행률. 초과 수행은 100%에서 cap한다."""
    if daily_target_count <= 0:
        return 0.0
    capped = min(max(completed_count, 0), daily_target_count)
    return round(capped / daily_target_count * 100, 1)


class ChallengeCoreService:
    """챌린지 시작·중단·공략 점수 누적 핵심 규칙."""

    async def start_from_recommendations(
        self,
        *,
        user_id: int,
        recommendation_ids: list[int],
        safety_confirmed: bool | None = None,
        now: datetime | None = None,
    ) -> list[UserChallenge]:
        if not 1 <= len(recommendation_ids) <= MAX_ACTIVE_CHALLENGES:
            raise AppError(ErrorCode.VALIDATION_ERROR)
        if len(set(recommendation_ids)) != len(recommendation_ids):
            raise AppError(ErrorCode.VALIDATION_ERROR)

        recommendations = await ChallengeRecommendation.filter(
            id__in=recommendation_ids,
            user_id=user_id,
        ).all()
        if len(recommendations) != len(recommendation_ids):
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)

        by_id = {item.id: item for item in recommendations}
        ordered_recommendations = [by_id[item_id] for item_id in recommendation_ids]
        challenge_ids = [item.challenge_id for item in ordered_recommendations]

        challenges = await Challenge.filter(id__in=challenge_ids, is_enabled=True).all()
        if len(challenges) != len(set(challenge_ids)):
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)
        challenge_by_id = {item.id: item for item in challenges}
        ordered_challenges = [challenge_by_id[item.challenge_id] for item in ordered_recommendations]

        if len(set(challenge_ids)) != len(challenge_ids):
            raise AppError(ErrorCode.CHLG_ALREADY_ACTIVE)

        active_count = await UserChallenge.filter(
            user_id=user_id,
            status=UserChallengeStatus.ACTIVE,
        ).count()
        if active_count + len(ordered_challenges) > MAX_ACTIVE_CHALLENGES:
            raise AppError(ErrorCode.CHLG_LIMIT_EXCEEDED)

        already_active = await UserChallenge.filter(
            user_id=user_id,
            challenge_id__in=challenge_ids,
            status=UserChallengeStatus.ACTIVE,
        ).exists()
        if already_active:
            raise AppError(ErrorCode.CHLG_ALREADY_ACTIVE)

        if any(ch.safety_check_required for ch in ordered_challenges) and safety_confirmed is not True:
            raise AppError(ErrorCode.CHLG_SAFETY_CONFIRMATION_REQUIRED)

        current = now or datetime.now(config.TIMEZONE)
        start_date = current.date()
        created: list[UserChallenge] = []
        for recommendation, challenge in zip(ordered_recommendations, ordered_challenges, strict=True):
            user_challenge = await UserChallenge.create(
                user_id=user_id,
                challenge_id=challenge.id,
                recommendation_id=recommendation.id,
                source_prediction_id=None,
                status=UserChallengeStatus.ACTIVE,
                start_date=start_date,
                end_date=start_date + timedelta(days=challenge.duration_days - 1),
                daily_target_count_snapshot=challenge.daily_target_count,
                target_value_snapshot=challenge.target_value,
                duration_days_snapshot=challenge.duration_days,
            )
            created.append(user_challenge)
            recommendation.action = RecommendationAction.ACCEPTED
            recommendation.acted_at = current
            recommendation.consecutive_reject_count = 0
            await recommendation.save(update_fields=["action", "acted_at", "consecutive_reject_count"])
        return created

    async def stop(
        self,
        *,
        user_id: int,
        user_challenge_id: int,
        stop_reason: str | None = None,
        now: datetime | None = None,
    ) -> UserChallenge:
        item = await UserChallenge.get_or_none(id=user_challenge_id, user_id=user_id)
        if item is None:
            raise AppError(ErrorCode.CHLG_NOT_FOUND)
        if item.status != UserChallengeStatus.ACTIVE:
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
        item.status = UserChallengeStatus.ABANDONED
        item.stopped_at = now or datetime.now(config.TIMEZONE)

        update_fields = ["status", "stopped_at", "updated_at"]

        if stop_reason is not None:
            item.stop_reason = stop_reason
            update_fields.append("stop_reason")

        await item.save(update_fields=update_fields)
        return item

    async def add_weekly_progress(
        self,
        *,
        user_id: int,
        factor_key: str | None,
        progress_value: int,
        occurred_at: datetime | None = None,
    ) -> list[UserMonster]:
        """REQ-CHLG-007: 수행 성공 시 공략 점수만 올린다."""
        if factor_key is None or progress_value <= 0:
            return []
        current = occurred_at or datetime.now(config.TIMEZONE)
        week_start = week_start_for(current)
        monsters = await Monster.filter(is_enabled=True).all()
        matched = [monster for monster in monsters if factor_key in monster.factor_keys]
        updated: list[UserMonster] = []
        for monster in matched:
            user_monster, _ = await UserMonster.get_or_create(user_id=user_id, monster_id=monster.id)
            if user_monster.progress_week_start != week_start:
                user_monster.weekly_progress = 0
                user_monster.progress_week_start = week_start
            user_monster.weekly_progress = min(
                100,
                user_monster.weekly_progress + progress_value,
            )
            await user_monster.save(update_fields=["weekly_progress", "progress_week_start", "updated_at"])
            updated.append(user_monster)
        return updated
