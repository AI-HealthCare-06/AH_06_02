from datetime import datetime, timedelta
from decimal import Decimal

from tortoise.contrib.test import TestCase

from app.core import config
from app.core.errors import AppError
from app.models.challenges import (
    Challenge,
    ChallengeCategory,
    ChallengeLog,
    ChallengeTimerSession,
    GoalType,
    OccurrenceStatus,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
    VerificationMethod,
    VerificationType,
)
from app.models.users import User
from app.services.challenge_timers import ChallengeTimerService, timer_body
from app.services.challenges import ChallengeCoreService

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=config.TIMEZONE)


class TestChallengeTimers(TestCase):
    async def prepare(self) -> tuple[User, UserChallenge]:
        user = await User.create(email="timer@example.com", nickname="타이머 검증", password_hash="x")
        challenge = await Challenge.create(
            code="TIMER",
            title="10분 걷기",
            category=ChallengeCategory.ACTIVITY,
            goal_type=GoalType.DURATION,
            verification_type=VerificationType.TIMER,
            target_value=10,
            unit="분",
        )
        mission = await UserChallenge.create(
            user_id=user.id,
            challenge_id=challenge.id,
            start_date=NOW.date(),
            end_date=NOW.date(),
            daily_target_count_snapshot=1,
            duration_days_snapshot=1,
            target_value_snapshot=Decimal("10"),
        )
        await UserChallengeOccurrence.create(user_challenge_id=mission.id, scheduled_date=NOW.date())
        return user, mission

    async def test_server_duration_and_retry_preserve_start_and_only_complete_once(self) -> None:
        user, mission = await self.prepare()
        service = ChallengeTimerService()
        first = await service.start(user.id, mission.id, None, NOW)
        second = await service.start(user.id, mission.id, None, NOW + timedelta(minutes=1))
        assert first["timer_session_id"] == second["timer_session_id"]
        assert first["started_at"] == second["started_at"]
        assert second["elapsed_seconds"] == 60
        timer = await ChallengeTimerSession.get(id=first["timer_session_id"])
        assert timer_body(timer, NOW + timedelta(minutes=10))["ready"] is True
        for current in [NOW + timedelta(minutes=9, seconds=59), NOW + timedelta(days=1)]:
            with self.assertRaises(AppError):
                await service.validate(user.id, mission.id, timer.id, None, current, current)
        current = NOW + timedelta(minutes=10)
        result = await ChallengeCoreService().record_log(
            user_id=user.id,
            user_challenge_id=mission.id,
            occurred_at=current,
            context_slot=None,
            value=Decimal("999"),
            verification_method=VerificationMethod.TIMER,
            evidence_url=None,
            timer_session_id=timer.id,
            now=current,
        )
        assert result.log.value == Decimal("10")
        assert result.reward_draw_id is not None
        assert (await ChallengeTimerSession.get(id=timer.id)).completed_log_id == result.log.id
        assert (await UserChallengeOccurrence.get(id=timer.occurrence_id)).status == OccurrenceStatus.COMPLETED
        with self.assertRaises(AppError):
            await service.validate(user.id, mission.id, timer.id, None, current, current)
        assert await ChallengeLog.all().count() == 1

    async def test_missing_ownership_unsupported_type_and_wrong_slot_are_rejected(self) -> None:
        user, mission = await self.prepare()
        other = await User.create(email="timer-other@example.com", nickname="다른 사용자", password_hash="x")
        service = ChallengeTimerService()
        with self.assertRaises(AppError):
            await service.start(other.id, mission.id, None, NOW)
        with self.assertRaises(AppError):
            await service.start(user.id, mission.id, "lunch", NOW)
        timer = await service.start(user.id, mission.id, None, NOW)
        with self.assertRaises(AppError):
            await service.get(other.id, mission.id, timer["timer_session_id"])
        with self.assertRaises(AppError):
            await service.validate(other.id, mission.id, timer["timer_session_id"], None, NOW, NOW)
        with self.assertRaises(AppError):
            await service.prepare_log(
                user.id, mission.id, timer["timer_session_id"], VerificationMethod.PHOTO, None, NOW, NOW, None
            )
        assert (await service.get(user.id, mission.id, timer["timer_session_id"]))["completed"] is False
        mission.status = UserChallengeStatus.ABANDONED
        await mission.save()
        with self.assertRaises(AppError):
            await service.start(user.id, mission.id, None, NOW)
