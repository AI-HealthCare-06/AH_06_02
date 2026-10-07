"""같은 날 재시작 (10/07 A·D 합의).

날짜로 막지 않고, 같은 사용자·같은 챌린지의 이전 인스턴스에서 이미 인정 완료한 기회를 새 인스턴스에서 뺀다.
하루 집계(중복 슬롯·XP 분배)도 사용자 + challenge_id + KST 날짜로 센다.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from tortoise.contrib.test import TestCase, TruncationTestCase

from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeCategory,
    ChallengeLog,
    ChallengeRecommendation,
    ContextType,
    GoalType,
    Monster,
    MonsterState,
    OccurrenceStatus,
    RecommendationSourceType,
    Reward,
    RewardKind,
    RewardMotivationType,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserMonster,
    UserReward,
    VerificationMethod,
    VerificationType,
)
from app.models.users import User
from app.services.attack_cycles import CYCLE_POLICY_VERSION
from app.services.challenges import ChallengeCoreService, LogResult
from app.tests.d_fixtures import make_card, make_cycle
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 7, 21, 0, tzinfo=KST)
TODAY = NOW.date()
TOMORROW = TODAY + timedelta(days=1)


async def _expect(code: ErrorCode, coro: Any) -> None:
    with pytest.raises(AppError) as exc:
        await coro
    assert exc.value.code == code


class _RestartCase(TestCase):
    service = ChallengeCoreService()

    async def _begin(
        self, email: str, code: str, factor: str, *, reward_xp: int | None = None
    ) -> tuple[User, UserAttackCycle, UserChallenge]:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        if reward_xp is not None:
            # 시작 전에 바꿔야 goal_config_snapshot 에 들어간다
            await Challenge.filter(code=code).update(reward_xp=reward_xp)
        user = await User.create(email=email, password_hash="x", nickname="t")
        cycle = await make_cycle(user.id, [factor])
        card = await make_card(user.id, await Challenge.get(code=code), cycle)
        [mission] = await self.service.start_from_recommendations(
            user_id=user.id, recommendation_ids=[card.id], safety_confirmed=True, now=NOW - timedelta(hours=12)
        )
        await cycle.refresh_from_db()
        return user, cycle, mission

    async def _restart(self, user: User, cycle: UserAttackCycle, mission: UserChallenge) -> UserChallenge:
        await self.service.stop(user_id=user.id, user_challenge_id=mission.id, now=NOW - timedelta(minutes=30))
        card = await make_card(user.id, await Challenge.get(id=mission.challenge_id), cycle)
        [restarted] = await self.service.start_from_recommendations(
            user_id=user.id, recommendation_ids=[card.id], safety_confirmed=True, now=NOW - timedelta(minutes=20)
        )
        return restarted

    async def _log(self, mission: UserChallenge, *, slot: str | None = None, value: str | None = None) -> LogResult:
        challenge = await Challenge.get(id=mission.challenge_id)
        return await self.service.record_log(
            user_id=mission.user_id,
            user_challenge_id=mission.id,
            occurred_at=NOW - timedelta(minutes=10),
            context_slot=slot,
            value=Decimal(value) if value else None,
            verification_method=VerificationMethod(str(challenge.verification_type)),
            evidence_url=None,
            now=NOW,
        )

    @staticmethod
    async def _planned(mission: UserChallenge, day: Any) -> list[tuple[str, int]]:
        rows = await UserChallengeOccurrence.filter(user_challenge_id=mission.id, scheduled_date=day).order_by(
            "slot_code", "sequence_no"
        )
        return [(row.slot_code, row.sequence_no) for row in rows]


class TestSlotCardRestart(_RestartCase):
    async def test_lunch_done_then_restart_leaves_only_dinner_today(self) -> None:
        user, cycle, old = await self._begin("restart-lunch@example.com", "CH_WALK_AFTER_MEAL", "physical_activity_low")
        lunch = await self._log(old, slot="lunch", value="10")
        assert lunch.log.xp_granted == 18

        new = await self._restart(user, cycle, old)

        assert await self._planned(new, TODAY) == [("dinner", 1)]
        assert await self._planned(new, TOMORROW) == [("dinner", 1), ("lunch", 1)]
        # 점심은 인스턴스를 넘어 다시 인정되지 않는다
        await _expect(ErrorCode.CHLG_LOG_DUPLICATED, self._log(new, slot="lunch", value="10"))
        dinner = await self._log(new, slot="dinner", value="10")
        assert dinner.log.xp_granted == 18
        assert (await User.get(id=user.id)).total_xp == 36
        # 이전 완료 로그를 새 인스턴스로 복사하지 않는다
        assert await ChallengeLog.filter(user_challenge_id=new.id).count() == 1

    async def test_restart_after_daily_target_has_no_extra_today(self) -> None:
        user, cycle, old = await self._begin("restart-full@example.com", "CH_WALK_AFTER_MEAL", "physical_activity_low")
        await self._log(old, slot="lunch", value="10")
        await self._log(old, slot="dinner", value="10")

        new = await self._restart(user, cycle, old)

        assert await self._planned(new, TODAY) == []
        assert await self._planned(new, TOMORROW) == [("dinner", 1), ("lunch", 1)]
        for slot in ("lunch", "dinner"):
            await _expect(ErrorCode.CHLG_LOG_DUPLICATED, self._log(new, slot=slot, value="10"))
        assert (await User.get(id=user.id)).total_xp == 36
        # 수행률 분모는 그 인스턴스에 배정한 기회다. 당일 0 개 + 남은 날 2 개씩
        days_left = (new.end_date - TODAY).days
        assert await UserChallengeOccurrence.filter(user_challenge_id=new.id).count() == days_left * 2


class TestNoSlotCardRestart(_RestartCase):
    async def test_daily_count_and_xp_cap_span_instances(self) -> None:
        user, cycle, old = await self._begin("restart-stand@example.com", "CH_STAND_HOURLY", "sedentary_time_high")
        first = [await self._log(old, value="3") for _ in range(2)]
        assert [item.log.xp_granted for item in first] == [12, 12]

        new = await self._restart(user, cycle, old)

        # 회차 번호를 1 부터 다시 세지 않는다. 이미 2 회 했으니 3 회차만 남는다
        assert await self._planned(new, TODAY) == [("", 3)]
        third = await self._log(new, value="3")
        fourth = await self._log(new, value="3")
        assert (third.log.xp_granted, third.log.reward_eligible) == (12, True)
        assert (fourth.log.xp_granted, fourth.log.reward_eligible) == (0, False)
        assert (await User.get(id=user.id)).total_xp == 36
        completed = await UserChallengeOccurrence.filter(
            user_challenge_id__in=[old.id, new.id], scheduled_date=TODAY, status=OccurrenceStatus.COMPLETED
        ).count()
        assert completed == 3

    async def test_remainder_goes_to_the_nth_completion_across_instances(self) -> None:
        # 나머지가 생기도록 하루 XP 를 10 으로 둔다. 10 // 3 = 3, 나머지 1
        user, cycle, old = await self._begin(
            "restart-remainder@example.com", "CH_STAND_HOURLY", "sedentary_time_high", reward_xp=10
        )
        assert [(await self._log(old, value="3")).log.xp_granted for _ in range(2)] == [3, 3]

        new = await self._restart(user, cycle, old)
        third = await self._log(new, value="3")

        # 이전 인스턴스 2 회를 포함한 그날 3 번째 인정에 나머지가 붙는다
        assert third.log.xp_granted == 4
        assert (await User.get(id=user.id)).total_xp == 10


class TestExtraSlotIsNotRestored(_RestartCase):
    async def test_stopping_an_extra_mission_does_not_return_the_slot(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        user = await User.create(email="restart-extra@example.com", password_hash="x", nickname="t")
        cycle = await make_cycle(
            user.id, ["physical_activity_low", "sedentary_time_high"], start=TODAY - timedelta(days=10)
        )
        walk = await make_card(user.id, await Challenge.get(code="CH_WALK_AFTER_MEAL"), cycle)
        [extra] = await self.service.start_from_recommendations(user_id=user.id, recommendation_ids=[walk.id], now=NOW)
        await cycle.refresh_from_db()
        assert cycle.extra_added_count == 1

        await self.service.stop(user_id=user.id, user_challenge_id=extra.id, now=NOW)
        stand = await make_card(user.id, await Challenge.get(code="CH_STAND_HOURLY"), cycle)

        await _expect(
            ErrorCode.CHLG_LIMIT_EXCEEDED,
            self.service.start_from_recommendations(user_id=user.id, recommendation_ids=[stand.id], now=NOW),
        )
        await cycle.refresh_from_db()
        assert cycle.extra_added_count == 1


# ---------------------------------------------------------------- 동시 요청
# TestCase 는 테스트 하나를 연결 하나의 트랜잭션에 묶어 진짜 동시 요청을 만들 수 없다.
# 이 테스트는 TruncationTestCase 로 연결 풀에서 동시에 보낸다. 끝나면 테이블을 비운다.

RACE_CODE = "T-RACE-WALK"
RACE_ROUNDS = 6


async def _race_round(round_no: int, challenge: Challenge, monster: Monster) -> dict[str, Any]:
    service = ChallengeCoreService()
    user = await User.create(email=f"race-{round_no}@example.com", password_hash="x", nickname="t")
    target = await UserMonster.create(user_id=user.id, monster_id=monster.id, impact_score=80, state=MonsterState.RAGE)
    cycle = await UserAttackCycle.create(
        user_id=user.id,
        target_user_monster_id=target.id,
        status=AttackCycleStatus.DRAFT,
        policy_version=CYCLE_POLICY_VERSION,
    )

    async def card() -> ChallengeRecommendation:
        return await ChallengeRecommendation.create(
            user_id=user.id,
            challenge_id=challenge.id,
            cycle_id=cycle.id,
            source_type=RecommendationSourceType.PREDICTION_PERSONAL,
            factor_key=challenge.factor_key,
            rank=1,
            recommended_at=datetime.now(KST),
        )

    [old] = await service.start_from_recommendations(user_id=user.id, recommendation_ids=[(await card()).id])
    new_card = await card()

    def lunch(mission_id: int) -> Any:
        return service.record_log(
            user_id=user.id,
            user_challenge_id=mission_id,
            occurred_at=datetime.now(KST),
            context_slot="lunch",
            value=Decimal("10"),
            verification_method=VerificationMethod.TIMER,
            evidence_url=None,
        )

    async def stop_then_restart() -> list[UserChallenge]:
        await service.stop(user_id=user.id, user_challenge_id=old.id)
        return await service.start_from_recommendations(user_id=user.id, recommendation_ids=[new_card.id])

    # 짝수 라운드는 이전 인스턴스 점심을 먼저 인정받는다. 동시 실행 순서로는 이 흐름을 보장할 수 없어서다
    # (record_log 가 잠금 전에 주기 종료를 확인하느라 늘 중단보다 늦게 잠금에 닿는다).
    outcomes: list[Any] = []
    if round_no % 2 == 0:
        outcomes.append(await lunch(old.id))
    # 중단→재시작과 이전 인스턴스의 같은 슬롯 수행을 동시에 보낸다
    outcomes += list(await asyncio.gather(stop_then_restart(), lunch(old.id), return_exceptions=True))
    new = await UserChallenge.filter(user_id=user.id).exclude(id=old.id).first()
    assert new is not None, outcomes
    # 재시작한 인스턴스로도 같은 점심을 동시에 두 번 보낸다
    outcomes += list(await asyncio.gather(lunch(new.id), lunch(new.id), return_exceptions=True))

    missions = [old.id, new.id]
    today = datetime.now(KST).date()
    logs = await ChallengeLog.filter(user_challenge_id__in=missions, log_date=today, context_slot="lunch")
    completed = await UserChallengeOccurrence.filter(
        user_challenge_id__in=missions, scheduled_date=today, slot_code="lunch", status=OccurrenceStatus.COMPLETED
    ).count()
    unexpected = [item for item in outcomes if isinstance(item, BaseException) and not isinstance(item, AppError)]
    return {
        "user_id": user.id,
        "lunch_logs": len(logs),
        "accepted": sum(log.reward_eligible for log in logs),
        "completed": completed,
        "xp_logged": sum(log.xp_granted for log in logs),
        "total_xp": (await User.get(id=user.id)).total_xp,
        "rewards": await UserReward.filter(user_id=user.id).count(),
        "weekly_progress": (await UserMonster.get(id=target.id)).weekly_progress,
        "unexpected": unexpected,
        "accepted_on_old": sum(log.reward_eligible for log in logs if log.user_challenge_id == old.id),
    }


class TestConcurrentRestart(TruncationTestCase):
    async def test_concurrent_stop_restart_and_same_slot_do_not_double_count(self) -> None:
        challenge = await Challenge.create(
            code=RACE_CODE,
            title="경합 식후 걷기",
            category=ChallengeCategory.ACTIVITY,
            factor_key="physical_activity_low",
            goal_type=GoalType.DURATION,
            target_value=Decimal("10"),
            daily_target_count=2,
            verification_type=VerificationType.TIMER,
            context_type=ContextType.MEAL,
            context_slots=["lunch", "dinner"],
            reward_xp=36,
            progress_value=10,
        )
        monster = await Monster.create(code="t-race", no=901, name="경합", factor_keys=["physical_activity_low"])
        await Reward.create(
            code="gluco_blade",
            name="글루코 블레이드",
            motivation_type=RewardMotivationType.GROW,
            reward_kind=RewardKind.ITEM,
            unlock_condition="테스트",
            linked_challenge_code=RACE_CODE,
        )

        results = [await _race_round(round_no, challenge, monster) for round_no in range(RACE_ROUNDS)]

        for result in results:
            assert result["unexpected"] == []
            # 인스턴스를 넘어 같은 날 점심은 기록도 인정도 한 번뿐이다
            assert result["lunch_logs"] <= 1
            assert result["accepted"] == result["completed"] <= 1
            assert result["total_xp"] == result["xp_logged"] == 18 * result["accepted"]
            assert result["rewards"] == result["accepted"]
            assert result["weekly_progress"] == 10 * result["accepted"]
            # 재시작이 항상 일어나는 흐름이라, 점심은 어느 인스턴스에서든 정확히 한 번 인정된다
            assert result["accepted"] == 1
        # 짝수 라운드는 이전 인스턴스에서 인정된 뒤 재시작했다. 인스턴스를 넘는 중복 방어를 실제로 거쳤다
        assert [result["accepted_on_old"] for result in results[::2]] == [1] * len(results[::2])
