"""기기 시계·입력값 대신 서버 시각으로 예정 기회 타이머를 검사한다."""

import math
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeTimerSession,
    OccurrenceStatus,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
    VerificationMethod,
    VerificationType,
)
from app.services.attack_cycles import lock_user


def kst(value: datetime) -> datetime:
    return value.replace(tzinfo=config.TIMEZONE) if value.tzinfo is None else value.astimezone(config.TIMEZONE)


def timer_body(timer: ChallengeTimerSession, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(config.TIMEZONE)
    # 멈춘 시간은 경과 시간에 넣지 않는다. 멈춰 있는 동안은 멈춘 시각에서 시간이 그친다
    paused_for = timer.paused_seconds + (
        (kst(current) - kst(timer.paused_at)).total_seconds() if timer.paused_at is not None else 0
    )
    elapsed = max(0, math.floor((kst(current) - kst(timer.started_at)).total_seconds() - paused_for))
    return {
        "timer_session_id": timer.id,
        "occurrence_id": timer.occurrence_id,
        "started_at": timer.started_at,
        "target_seconds": timer.target_seconds,
        "elapsed_seconds": min(elapsed, timer.target_seconds),
        "ready": elapsed >= timer.target_seconds
        and kst(current) < kst(timer.expires_at)
        and timer.completed_log_id is None,
        "expires_at": timer.expires_at,
        "completed": timer.completed_log_id is not None,
        "paused": timer.paused_at is not None,
    }


class ChallengeTimerService:
    async def start(
        self, user_id: int, mission_id: int, slot: str | None, now: datetime | None = None
    ) -> dict[str, Any]:
        current = now or datetime.now(config.TIMEZONE)
        async with in_transaction():
            await lock_user(user_id)
            mission = await UserChallenge.select_for_update().get_or_none(id=mission_id, user_id=user_id)
            if mission is None:
                raise AppError(ErrorCode.CHLG_NOT_FOUND)
            if (
                mission.status != UserChallengeStatus.ACTIVE
                or not mission.start_date <= current.date() <= mission.end_date
            ):
                raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
            if mission.cycle_id:
                cycle = await UserAttackCycle.select_for_update().get_or_none(id=mission.cycle_id, user_id=user_id)
                if cycle is None or cycle.status != AttackCycleStatus.ACTIVE:
                    raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
            challenge = await Challenge.get(id=mission.challenge_id)
            if challenge.verification_type != VerificationType.TIMER or mission.target_value_snapshot is None:
                raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
            slots = challenge.context_slots or []
            if (slots and slot not in slots) or (not slots and slot is not None):
                raise AppError(ErrorCode.VALIDATION_ERROR)
            occurrence = (
                await UserChallengeOccurrence.select_for_update()
                .filter(
                    user_challenge_id=mission.id,
                    scheduled_date=current.date(),
                    slot_code=slot or "",
                    status=OccurrenceStatus.PLANNED,
                )
                .order_by("sequence_no")
                .first()
            )
            if occurrence is None:
                raise AppError(ErrorCode.CHLG_LOG_DUPLICATED)
            timer, _ = await ChallengeTimerSession.get_or_create(
                occurrence_id=occurrence.id,
                defaults={
                    "user_id": user_id,
                    "user_challenge_id": mission.id,
                    "started_at": current,
                    "target_seconds": math.ceil(mission.target_value_snapshot * 60),
                    "expires_at": datetime.combine(current.date() + timedelta(days=1), time.min, config.TIMEZONE),
                },
            )
            return timer_body(timer, current)

    async def get(self, user_id: int, mission_id: int, timer_id: int) -> dict[str, Any]:
        timer = await ChallengeTimerSession.get_or_none(id=timer_id, user_id=user_id, user_challenge_id=mission_id)
        if timer is None:
            raise AppError(ErrorCode.CHLG_NOT_FOUND)
        return timer_body(timer)

    async def _changeable(self, user_id: int, mission_id: int, timer_id: int, now: datetime) -> ChallengeTimerSession:
        """사용자 잠금을 얻은 트랜잭션 안에서 호출한다. 완료·만료 세션은 멈추거나 이어할 수 없다."""
        timer = await ChallengeTimerSession.select_for_update().get_or_none(
            id=timer_id, user_id=user_id, user_challenge_id=mission_id
        )
        if timer is None:
            raise AppError(ErrorCode.CHLG_NOT_FOUND)
        if timer.completed_log_id is not None or kst(now) >= kst(timer.expires_at):
            raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
        return timer

    async def pause(self, user_id: int, mission_id: int, timer_id: int, now: datetime | None = None) -> dict[str, Any]:
        """CHLG-13. 이미 멈춘 세션은 그대로 돌려준다."""
        current = now or datetime.now(config.TIMEZONE)
        async with in_transaction():
            await lock_user(user_id)
            timer = await self._changeable(user_id, mission_id, timer_id, current)
            if timer.paused_at is None:
                timer.paused_at = current
                await timer.save(update_fields=["paused_at"])
            return timer_body(timer, current)

    async def resume(self, user_id: int, mission_id: int, timer_id: int, now: datetime | None = None) -> dict[str, Any]:
        """CHLG-14. 멈춘 시간을 paused_seconds 에 더한다. 진행 중 세션은 그대로 돌려준다."""
        current = now or datetime.now(config.TIMEZONE)
        async with in_transaction():
            await lock_user(user_id)
            timer = await self._changeable(user_id, mission_id, timer_id, current)
            if timer.paused_at is not None:
                timer.paused_seconds += max(0, math.floor((kst(current) - kst(timer.paused_at)).total_seconds()))
                timer.paused_at = None
                await timer.save(update_fields=["paused_at", "paused_seconds"])
            return timer_body(timer, current)

    async def validate(
        self, user_id: int, mission_id: int, timer_id: int, slot: str | None, occurred: datetime, now: datetime
    ) -> ChallengeTimerSession:
        """사용자·미션 잠금을 얻은 수행 기록 트랜잭션 안에서 호출한다."""
        timer = await ChallengeTimerSession.select_for_update().get_or_none(
            id=timer_id, user_id=user_id, user_challenge_id=mission_id
        )
        if timer is None:
            raise AppError(ErrorCode.CHLG_NOT_FOUND)
        occurrence = await UserChallengeOccurrence.get_or_none(
            id=timer.occurrence_id,
            user_challenge_id=mission_id,
            slot_code=slot or "",
            scheduled_date=kst(now).date(),
            status=OccurrenceStatus.PLANNED,
        )
        if occurrence is None or not timer_body(timer, now)["ready"] or kst(occurred) < kst(timer.started_at):
            raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
        return timer

    @staticmethod
    def minutes(timer: ChallengeTimerSession) -> Decimal:
        return Decimal(timer.target_seconds) / 60

    async def prepare_log(
        self,
        user_id: int,
        mission_id: int,
        timer_id: int | None,
        method: VerificationMethod,
        slot: str | None,
        occurred: datetime,
        now: datetime,
        value: Decimal | None,
    ) -> tuple[ChallengeTimerSession | None, Decimal | None]:
        if timer_id is None:
            return None, value
        if method != VerificationMethod.TIMER:
            raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
        timer = await self.validate(user_id, mission_id, timer_id, slot, occurred, now)
        return timer, self.minutes(timer)

    @staticmethod
    async def consume(timer: ChallengeTimerSession | None, occurrence_id: int, log_id: int) -> None:
        if timer is None:
            return
        if timer.occurrence_id != occurrence_id:
            raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
        timer.completed_log_id = log_id
        await timer.save(update_fields=["completed_log_id"])
