"""공략 주기. 한 번에 한 캐릭터만 공략한다 (REQ-RECO-006 · AGENTS.md 공략 사이클, 2026-10-04 확정)."""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from tortoise.transactions import in_transaction

from app.core import config
from app.models.challenges import (
    AttackCycleStatus,
    Monster,
    MonsterState,
    OccurrenceStatus,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
    UserMonster,
)

#: 이 버전이 가리키는 규칙은 AGENTS.md 공략 사이클 절이다.
#: D28 공통 종료, 초기 최대 2개, 2주차부터 주기당 1개 추가, 동시 최대 3개.
#: 주기를 만들 때 넣고, 진행 중인 주기의 값은 덮어쓰지 않는다.
CYCLE_POLICY_VERSION = "CYCLE-20261004-v1"

CYCLE_DAYS = 28
INITIAL_MAX_CHALLENGES = 2
EXTRA_FROM_DAY = 7
MAX_EXTRA_PER_CYCLE = 1
MAX_ACTIVE_CHALLENGES = 3

#: 공략 대상이 될 수 있는 상태 (MNSTR-01)
TARGETABLE_STATES = (MonsterState.RAGE, MonsterState.CAUTION, MonsterState.STABLE)


def today_kst(now: datetime | None = None) -> date:
    return (now or datetime.now(config.TIMEZONE)).astimezone(config.TIMEZONE).date()


def cycle_day(cycle: UserAttackCycle, today: date) -> int | None:
    """D0 부터 센 오늘의 날짜 번호. 시작 전이면 None."""
    if cycle.start_date is None:
        return None
    return (today - cycle.start_date).days


def cycle_week(cycle: UserAttackCycle, today: date) -> int | None:
    """D0~D6=1주차, D7~D13=2주차. D28 이후는 진행 중 주차를 표시하지 않는다. 저장하지 않고 계산한다."""
    day = cycle_day(cycle, today)
    if day is None or not 0 <= day < CYCLE_DAYS:
        return None
    return day // 7 + 1


def completion_rate(completed: int, planned: int) -> Decimal | None:
    """인정 완료 ÷ 예정 기회. 분모 0이면 NULL."""
    if planned <= 0:
        return None
    return (Decimal(completed) / Decimal(planned)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class AttackCycleService:
    async def close_expired(self, user_id: int, today: date, now: datetime | None = None) -> None:
        """D28 경계를 지난 active 주기를 닫는다 (REQ-CHLG-011).

        같은 주기의 미션은 투입 시점과 관계없이 함께 끝나고 이월하지 않는다.
        남은 예정 기회는 missed 로 두어 분모에만 남긴다. 습관 졸업은 판정하지 않는다.
        """
        expired = await UserAttackCycle.filter(user_id=user_id, status=AttackCycleStatus.ACTIVE, end_date__lt=today)
        current = now or datetime.now(config.TIMEZONE)
        for cycle in expired:
            async with in_transaction():
                missions = await UserChallenge.filter(cycle_id=cycle.id, status=UserChallengeStatus.ACTIVE)
                for mission in missions:
                    await UserChallengeOccurrence.filter(
                        user_challenge_id=mission.id, status=OccurrenceStatus.PLANNED
                    ).update(status=OccurrenceStatus.MISSED)
                    await self.summarize(mission, current, cycle.policy_version)
                    # 화면에는 "기간 종료"로 표시한다
                    mission.status = UserChallengeStatus.GRADUATED
                    await mission.save(update_fields=["status", "updated_at"])
                cycle.status = AttackCycleStatus.COMPLETED
                await cycle.save(update_fields=["status", "updated_at"])

    async def summarize(self, mission: UserChallenge, now: datetime, policy_version: str) -> None:
        occurrences = UserChallengeOccurrence.filter(user_challenge_id=mission.id)
        planned = await occurrences.count()
        completed = await occurrences.filter(status=OccurrenceStatus.COMPLETED).count()
        await UserChallenge.filter(id=mission.id).update(
            planned_occurrence_count=planned,
            completed_occurrence_count=completed,
            completion_rate=completion_rate(completed, planned),
            summary_computed_at=now,
            summary_policy_version=policy_version,
        )

    async def get_active(self, user_id: int) -> UserAttackCycle | None:
        return await UserAttackCycle.get_or_none(user_id=user_id, status=AttackCycleStatus.ACTIVE)

    async def get_current(self, user_id: int) -> UserAttackCycle | None:
        """active 주기, 없으면 draft 주기."""
        active = await self.get_active(user_id)
        if active is not None:
            return active
        return await UserAttackCycle.filter(user_id=user_id, status=AttackCycleStatus.DRAFT).order_by("-id").first()

    async def select_target(self, user_id: int) -> UserMonster | None:
        """위협도 1순위 캐릭터 (REQ-RECO-006). 위협도가 같으면 도감 번호가 앞선 쪽."""
        monsters = {monster.id: monster for monster in await Monster.filter(is_enabled=True)}
        candidates = [
            item
            for item in await UserMonster.filter(
                user_id=user_id, state__in=list(TARGETABLE_STATES), impact_score__isnull=False
            )
            if item.monster_id in monsters
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (-(item.impact_score or 0), monsters[item.monster_id].no))

    async def get_or_create_for_recommendation(self, user_id: int) -> UserAttackCycle | None:
        """추천을 연결할 주기. active 가 있으면 그 주기, 없으면 draft 를 쓰거나 만든다.

        draft 는 기간이 없다. 추천 조회만으로 28일을 시작하지 않는다.
        주기 중에는 재측정 결과로 대상을 바꾸지 않는다.
        """
        current = await self.get_current(user_id)
        if current is not None:
            return current
        target = await self.select_target(user_id)
        if target is None:
            return None
        return await UserAttackCycle.create(
            user_id=user_id,
            target_user_monster_id=target.id,
            status=AttackCycleStatus.DRAFT,
            policy_version=CYCLE_POLICY_VERSION,
        )

    async def target_monster(self, cycle: UserAttackCycle) -> Monster:
        user_monster = await UserMonster.get(id=cycle.target_user_monster_id)
        return await Monster.get(id=user_monster.monster_id)

    def remaining_slots(self, cycle: UserAttackCycle, active_in_cycle: int, active_total: int, today: date) -> int:
        """이번에 더 시작할 수 있는 개수 (REQ-CHLG-002)."""
        overall = MAX_ACTIVE_CHALLENGES - active_total
        day = cycle_day(cycle, today)
        if cycle.status == AttackCycleStatus.DRAFT or day is None or day < EXTRA_FROM_DAY:
            by_cycle = INITIAL_MAX_CHALLENGES - active_in_cycle
        else:
            by_cycle = MAX_EXTRA_PER_CYCLE - cycle.extra_added_count
        return max(0, min(overall, by_cycle))


def cycle_end_for(start: date) -> date:
    """마지막 수행 가능 날짜 D0+27. 다음 날 00:00 KST 가 D28 종료 경계다."""
    return start + timedelta(days=CYCLE_DAYS - 1)
