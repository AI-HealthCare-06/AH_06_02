from datetime import date, datetime
from zoneinfo import ZoneInfo

from tortoise.contrib.test import TestCase

from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    Challenge,
    ChallengeCategory,
    ChallengeRecommendation,
    GoalType,
    Monster,
    RecommendationAction,
    RecommendationSourceType,
    UserChallenge,
    UserChallengeStatus,
    UserMonster,
)
from app.services.challenges import ChallengeCoreService, progress_rate, week_start_for

KST = ZoneInfo("Asia/Seoul")


async def make_challenge(
    *,
    code: str,
    factor_key: str | None = "smoking_current",
    safety_check_required: bool = False,
    duration_days: int = 7,
    progress_value: int = 10,
) -> Challenge:
    return await Challenge.create(
        code=code,
        title=code,
        category=ChallengeCategory.ACTIVITY,
        factor_key=factor_key,
        goal_type=GoalType.BOOLEAN,
        duration_days=duration_days,
        progress_value=progress_value,
        safety_check_required=safety_check_required,
    )


async def make_recommendation(
    *,
    user_id: int,
    challenge: Challenge,
    rank: int = 1,
) -> ChallengeRecommendation:
    return await ChallengeRecommendation.create(
        user_id=user_id,
        challenge_id=challenge.id,
        source_type=RecommendationSourceType.PREDICTION_PERSONAL,
        factor_key=challenge.factor_key or "bonus",
        rank=rank,
        recommended_at=datetime(2026, 9, 30, 12, 0, tzinfo=KST),
    )


def test_week_start_for_uses_monday() -> None:
    assert week_start_for(date(2026, 9, 30)) == date(2026, 9, 28)


def test_progress_rate_caps_at_100_and_handles_zero_target() -> None:
    assert progress_rate(0, 2) == 0.0
    assert progress_rate(1, 2) == 50.0
    assert progress_rate(2, 2) == 100.0
    assert progress_rate(5, 2) == 100.0
    assert progress_rate(1, 0) == 0.0


class TestChallengeCoreService(TestCase):
    async def test_start_from_recommendation_snapshots_master_values(self) -> None:
        service = ChallengeCoreService()
        challenge = await make_challenge(code="TEST-START-1", duration_days=14)
        recommendation = await make_recommendation(user_id=9101, challenge=challenge)

        created = await service.start_from_recommendations(
            user_id=9101,
            recommendation_ids=[recommendation.id],
            now=datetime(2026, 9, 30, 9, 0, tzinfo=KST),
        )

        assert len(created) == 1
        item = created[0]
        assert item.status == UserChallengeStatus.ACTIVE
        assert item.start_date == date(2026, 9, 30)
        assert item.end_date == date(2026, 10, 13)
        assert item.duration_days_snapshot == 14
        assert item.daily_target_count_snapshot == challenge.daily_target_count

        await recommendation.refresh_from_db()
        assert recommendation.action == RecommendationAction.ACCEPTED
        assert recommendation.consecutive_reject_count == 0

    async def test_start_requires_safety_confirmation_when_master_requires_it(self) -> None:
        service = ChallengeCoreService()
        challenge = await make_challenge(code="TEST-SAFE-1", safety_check_required=True)
        recommendation = await make_recommendation(user_id=9102, challenge=challenge)

        try:
            await service.start_from_recommendations(
                user_id=9102,
                recommendation_ids=[recommendation.id],
                safety_confirmed=None,
            )
        except AppError as exc:
            assert exc.code == ErrorCode.CHLG_SAFETY_CONFIRMATION_REQUIRED
        else:
            raise AssertionError("안전확인 없이 시작이 허용되었습니다.")

        assert await UserChallenge.filter(user_id=9102).count() == 0

    async def test_start_rejects_when_active_total_would_exceed_three(self) -> None:
        service = ChallengeCoreService()

        for index in range(2):
            challenge = await make_challenge(code=f"TEST-ACTIVE-{index}")
            await UserChallenge.create(
                user_id=9103,
                challenge_id=challenge.id,
                status=UserChallengeStatus.ACTIVE,
                start_date=date(2026, 9, 30),
                end_date=date(2026, 10, 6),
                daily_target_count_snapshot=1,
                target_value_snapshot=None,
                duration_days_snapshot=7,
            )

        recommendations: list[ChallengeRecommendation] = []
        for index in range(2):
            challenge = await make_challenge(code=f"TEST-NEW-{index}")
            recommendations.append(
                await make_recommendation(
                    user_id=9103,
                    challenge=challenge,
                    rank=index + 1,
                )
            )

        try:
            await service.start_from_recommendations(
                user_id=9103,
                recommendation_ids=[item.id for item in recommendations],
            )
        except AppError as exc:
            assert exc.code == ErrorCode.CHLG_LIMIT_EXCEEDED
        else:
            raise AssertionError("활성 챌린지 3개 제한이 적용되지 않았습니다.")

    async def test_start_rejects_same_challenge_when_already_active(self) -> None:
        service = ChallengeCoreService()
        challenge = await make_challenge(code="TEST-DUPLICATE-1")
        recommendation = await make_recommendation(user_id=9104, challenge=challenge)
        await UserChallenge.create(
            user_id=9104,
            challenge_id=challenge.id,
            status=UserChallengeStatus.ACTIVE,
            start_date=date(2026, 9, 30),
            end_date=date(2026, 10, 6),
            daily_target_count_snapshot=1,
            target_value_snapshot=None,
            duration_days_snapshot=7,
        )

        try:
            await service.start_from_recommendations(
                user_id=9104,
                recommendation_ids=[recommendation.id],
            )
        except AppError as exc:
            assert exc.code == ErrorCode.CHLG_ALREADY_ACTIVE
        else:
            raise AssertionError("같은 챌린지의 중복 시작이 허용되었습니다.")

    async def test_stop_marks_active_challenge_abandoned(self) -> None:
        service = ChallengeCoreService()
        challenge = await make_challenge(code="TEST-STOP-1")
        item = await UserChallenge.create(
            user_id=9105,
            challenge_id=challenge.id,
            status=UserChallengeStatus.ACTIVE,
            start_date=date(2026, 9, 30),
            end_date=date(2026, 10, 6),
            daily_target_count_snapshot=1,
            target_value_snapshot=None,
            duration_days_snapshot=7,
        )

        stopped = await service.stop(
            user_id=9105,
            user_challenge_id=item.id,
            stop_reason="사용자 중단",
            now=datetime(2026, 10, 1, 10, 0, tzinfo=KST),
        )

        assert stopped.status == UserChallengeStatus.ABANDONED
        assert stopped.stop_reason == "사용자 중단"
        assert stopped.stopped_at is not None

    async def test_stop_returns_not_found_for_other_users_challenge(self) -> None:
        service = ChallengeCoreService()
        challenge = await make_challenge(code="TEST-STOP-2")
        item = await UserChallenge.create(
            user_id=9106,
            challenge_id=challenge.id,
            status=UserChallengeStatus.ACTIVE,
            start_date=date(2026, 9, 30),
            end_date=date(2026, 10, 6),
            daily_target_count_snapshot=1,
            target_value_snapshot=None,
            duration_days_snapshot=7,
        )

        try:
            await service.stop(user_id=9999, user_challenge_id=item.id)
        except AppError as exc:
            assert exc.code == ErrorCode.CHLG_NOT_FOUND
        else:
            raise AssertionError("다른 사용자의 챌린지 접근이 허용되었습니다.")

    async def test_weekly_progress_updates_every_monster_linked_to_factor(self) -> None:
        service = ChallengeCoreService()
        first = await Monster.create(
            code="TEST-MON-A",
            no=9101,
            name="A",
            factor_keys=["smoking_current"],
        )
        second = await Monster.create(
            code="TEST-MON-B",
            no=9102,
            name="B",
            factor_keys=["smoking_current", "walking_low"],
        )

        updated = await service.add_weekly_progress(
            user_id=9107,
            factor_key="smoking_current",
            progress_value=40,
            occurred_at=datetime(2026, 9, 30, 15, 0, tzinfo=KST),
        )

        assert {item.monster_id for item in updated} == {first.id, second.id}

        rows = await UserMonster.filter(user_id=9107).all()
        assert len(rows) == 2
        assert all(item.weekly_progress == 40 for item in rows)
        assert all(item.progress_week_start == date(2026, 9, 28) for item in rows)

    async def test_weekly_progress_resets_when_calendar_week_changes(self) -> None:
        service = ChallengeCoreService()
        monster = await Monster.create(
            code="TEST-MON-C",
            no=9103,
            name="C",
            factor_keys=["walking_low"],
        )
        await UserMonster.create(
            user_id=9108,
            monster_id=monster.id,
            weekly_progress=90,
            progress_week_start=date(2026, 9, 28),
        )

        updated = await service.add_weekly_progress(
            user_id=9108,
            factor_key="walking_low",
            progress_value=20,
            occurred_at=datetime(2026, 10, 5, 0, 1, tzinfo=KST),
        )

        assert len(updated) == 1
        assert updated[0].weekly_progress == 20
        assert updated[0].progress_week_start == date(2026, 10, 5)

    async def test_bonus_challenge_does_not_change_weekly_progress(self) -> None:
        service = ChallengeCoreService()

        updated = await service.add_weekly_progress(
            user_id=9109,
            factor_key=None,
            progress_value=30,
        )

        assert updated == []
        assert await UserMonster.filter(user_id=9109).count() == 0
