"""승인된 단계표의 개인 목표로 챌린지를 시작하고 기록하는 규칙을 확인한다."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from tortoise.contrib.test import TestCase

from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    Challenge,
    ChallengeRecommendation,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
    VerificationMethod,
)
from app.services.challenge_goals import goal_policy
from app.services.challenge_timers import ChallengeTimerService
from app.services.challenges import ChallengeCoreService
from app.tests.d_fixtures import make_card, make_cycle
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 27, 21, 0, tzinfo=KST)
TODAY = NOW.date()


async def _seed() -> dict[str, Challenge]:
    await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
    return {item.code: item for item in await Challenge.all()}


def _proposal(challenge: Challenge, level: int, previous_level: int | None = None) -> dict[str, Any]:
    policy = goal_policy(challenge)
    assert policy is not None
    return {
        "policy_version": policy.version,
        "level": level,
        "basis": {"previous_level": previous_level if previous_level is not None else level},
    }


async def _personal_card(user_id: int, challenge: Challenge, proposal: dict[str, Any]) -> ChallengeRecommendation:
    cycle = await make_cycle(user_id, [challenge.factor_key or "physical_activity_low"])
    card = await make_card(user_id, challenge, cycle)
    await ChallengeRecommendation.filter(id=card.id).update(proposed_goal=proposal)
    return card


async def _expect(code: ErrorCode, coro: object) -> None:
    with pytest.raises(AppError) as exc:
        await coro  # type: ignore[misc]
    assert exc.value.code == code


class TestPersonalGoalStart(TestCase):
    async def test_personal_goal_card_starts_with_the_step_goal(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        card = await _personal_card(5001, walk, _proposal(walk, 1, previous_level=3))

        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=5001, recommendation_ids=[card.id], now=NOW
        )

        # 1단계: 아무 식사 뒤에나 10분, 하루 1회, easy
        assert mission.daily_target_count_snapshot == 1
        assert mission.target_value_snapshot == Decimal("10")
        snapshot = mission.goal_config_snapshot or {}
        assert snapshot["level"] == 1
        assert snapshot["difficulty"] == "easy"
        assert snapshot["daily_xp"] == 12
        assert snapshot["context_slots"] == []
        occurrences = await UserChallengeOccurrence.filter(user_challenge_id=mission.id)
        assert len(occurrences) == 28
        assert {item.slot_code for item in occurrences} == {""}

    async def test_fixed_goal_start_records_the_base_step(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        cycle = await make_cycle(5002, ["physical_activity_low"])
        card = await make_card(5002, walk, cycle)

        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=5002, recommendation_ids=[card.id], now=NOW
        )

        policy = goal_policy(walk)
        assert policy is not None
        snapshot = mission.goal_config_snapshot or {}
        # 다음 주기에 단계를 이어 가려면 기본 단계도 남긴다
        assert (snapshot["level"], snapshot["policy_version"]) == (policy.base_level, policy.version)
        assert mission.daily_target_count_snapshot == 2

    async def test_daily_xp_follows_the_step_difficulty(self) -> None:
        challenges = await _seed()
        cigarette = challenges["CH_DELAY_FIRST_CIG"]
        card = await _personal_card(5003, cigarette, _proposal(cigarette, 1, previous_level=2))
        service = ChallengeCoreService()
        [mission] = await service.start_from_recommendations(user_id=5003, recommendation_ids=[card.id], now=NOW)

        result = await service.record_log(
            user_id=5003,
            user_challenge_id=mission.id,
            occurred_at=NOW - timedelta(minutes=10),
            context_slot=None,
            value=None,
            verification_method=VerificationMethod.MANUAL,
            evidence_url=None,
            now=NOW,
        )

        # 마스터는 normal(24)이지만 1단계는 easy 라 하루 12
        assert result.log.xp_granted == 12

    async def test_step_missing_from_the_policy_is_refused(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        card = await _personal_card(5004, walk, _proposal(walk, 9))

        await _expect(
            ErrorCode.VALIDATION_ERROR,
            ChallengeCoreService().start_from_recommendations(user_id=5004, recommendation_ids=[card.id], now=NOW),
        )
        assert await UserChallenge.filter(user_id=5004).count() == 0

    async def test_goal_from_an_older_policy_version_is_refused(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        card = await _personal_card(5005, walk, {**_proposal(walk, 1), "policy_version": "P1-STEPS-OLD"})

        await _expect(
            ErrorCode.VALIDATION_ERROR,
            ChallengeCoreService().start_from_recommendations(user_id=5005, recommendation_ids=[card.id], now=NOW),
        )
        assert await UserChallenge.filter(user_id=5005).count() == 0

    async def test_challenge_without_policy_refuses_a_personal_goal(self) -> None:
        challenges = await _seed()
        smoke = challenges["CH_NO_SMOKE_TODAY"]
        card = await _personal_card(5006, smoke, {"policy_version": "x", "level": 1, "basis": {}})

        await _expect(
            ErrorCode.VALIDATION_ERROR,
            ChallengeCoreService().start_from_recommendations(user_id=5006, recommendation_ids=[card.id], now=NOW),
        )

    async def test_raised_step_needs_a_fresh_safety_check(self) -> None:
        challenges = await _seed()
        stand = challenges["CH_STAND_HOURLY"]
        # 마스터는 안전 확인이 필요 없는 챌린지지만 한 단계 올린 목표는 확인을 다시 받는다
        assert stand.safety_check_required is False
        card = await _personal_card(5007, stand, _proposal(stand, 3, previous_level=2))
        service = ChallengeCoreService()

        await _expect(
            ErrorCode.CHLG_SAFETY_CONFIRMATION_REQUIRED,
            service.start_from_recommendations(user_id=5007, recommendation_ids=[card.id], now=NOW),
        )
        [mission] = await service.start_from_recommendations(
            user_id=5007, recommendation_ids=[card.id], safety_confirmed=True, now=NOW
        )
        assert mission.daily_target_count_snapshot == 3

    async def test_log_and_timer_follow_the_step_slots(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        card = await _personal_card(5008, walk, _proposal(walk, 1, previous_level=3))
        service = ChallengeCoreService()
        [mission] = await service.start_from_recommendations(user_id=5008, recommendation_ids=[card.id], now=NOW)

        # 1단계는 슬롯 없이 하루 1회라 점심 슬롯으로는 타이머를 켤 수 없다
        await _expect(ErrorCode.VALIDATION_ERROR, ChallengeTimerService().start(5008, mission.id, "lunch", NOW))
        timer = await ChallengeTimerService().start(5008, mission.id, None, NOW)
        assert timer["occurrence_id"]

    async def test_restart_in_the_same_cycle_keeps_the_first_step(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        card = await _personal_card(5009, walk, _proposal(walk, 1, previous_level=3))
        service = ChallengeCoreService()
        [first] = await service.start_from_recommendations(user_id=5009, recommendation_ids=[card.id], now=NOW)
        await service.stop(user_id=5009, user_challenge_id=first.id, now=NOW)
        again = await make_card(5009, walk, await UserAttackCycle.get(id=first.cycle_id))
        await ChallengeRecommendation.filter(id=again.id).update(proposed_goal=_proposal(walk, 3))

        # 같은 날 하루 횟수가 바뀌면 이미 받은 XP 와 새 목표가 섞인다
        await _expect(
            ErrorCode.VALIDATION_ERROR,
            service.start_from_recommendations(user_id=5009, recommendation_ids=[again.id], now=NOW),
        )

    async def test_active_list_shows_the_step_title_and_slots(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        card = await _personal_card(5010, walk, _proposal(walk, 1, previous_level=3))
        service = ChallengeCoreService()
        await service.start_from_recommendations(user_id=5010, recommendation_ids=[card.id], now=NOW)

        [item], _ = await service.list_user_challenges(
            user_id=5010, status=UserChallengeStatus.ACTIVE, page=1, size=10, now=NOW
        )

        assert (item["title"], item["daily_target_count"], item["context_slots"]) == ("식후 걷기", 1, [])
        assert (item["goal_level"], item["intensity"]) == (1, None)

    async def _legacy_stopped(self, user_id: int, challenge: Challenge) -> UserAttackCycle:
        """단계표 적용 전에 시작했다가 중단한 미션. 스냅샷에 단계 정보가 없다."""
        cycle = await make_cycle(user_id, [challenge.factor_key or "physical_activity_low"], start=TODAY)
        await UserChallenge.create(
            user_id=user_id,
            challenge_id=challenge.id,
            cycle_id=cycle.id,
            status=UserChallengeStatus.ABANDONED,
            start_date=TODAY,
            end_date=cycle.end_date,
            daily_target_count_snapshot=challenge.daily_target_count,
            target_value_snapshot=challenge.target_value,
            duration_days_snapshot=28,
            goal_config_snapshot={
                "difficulty": str(challenge.difficulty),
                "daily_xp": challenge.reward_xp,
                "unit": "분",
            },
        )
        return cycle

    async def test_mission_started_before_the_step_table_restarts_on_the_same_goal(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        cycle = await self._legacy_stopped(5011, walk)
        card = await make_card(5011, walk, cycle)

        # 단계 정보가 없는 미션은 기본 단계로 본다. 목표가 같으니 다시 시작할 수 있다
        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=5011, recommendation_ids=[card.id], now=NOW
        )
        assert mission.daily_target_count_snapshot == 2

    async def test_mission_started_before_the_step_table_cannot_restart_on_another_step(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        cycle = await self._legacy_stopped(5012, walk)
        card = await make_card(5012, walk, cycle)
        await ChallengeRecommendation.filter(id=card.id).update(proposed_goal=_proposal(walk, 1))

        await _expect(
            ErrorCode.VALIDATION_ERROR,
            ChallengeCoreService().start_from_recommendations(user_id=5012, recommendation_ids=[card.id], now=NOW),
        )

    async def test_mission_whose_old_goal_differs_from_the_base_step_cannot_restart(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        cycle = await self._legacy_stopped(5013, walk)
        # 단계표 적용 전 마스터가 지금 기본 단계와 다른 목표였던 경우
        await UserChallenge.filter(user_id=5013).update(target_value_snapshot=Decimal("15"))
        card = await make_card(5013, walk, cycle)

        await _expect(
            ErrorCode.VALIDATION_ERROR,
            ChallengeCoreService().start_from_recommendations(user_id=5013, recommendation_ids=[card.id], now=NOW),
        )

    async def test_mission_from_an_older_policy_version_restarts_on_the_same_goal(self) -> None:
        challenges = await _seed()
        walk = challenges["CH_WALK_AFTER_MEAL"]
        cycle = await self._legacy_stopped(5014, walk)
        # 옛 단계표 버전의 1단계로 시작했던 미션. 목표는 지금 1단계와 같다(10분, 하루 1회, 슬롯 없음)
        await UserChallenge.filter(user_id=5014).update(
            daily_target_count_snapshot=1,
            target_value_snapshot=Decimal("10"),
            goal_config_snapshot={"level": 1, "policy_version": "P1-STEPS-OLD", "context_slots": []},
        )
        card = await make_card(5014, walk, cycle)
        await ChallengeRecommendation.filter(id=card.id).update(proposed_goal=_proposal(walk, 1))

        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=5014, recommendation_ids=[card.id], now=NOW
        )
        assert (mission.goal_config_snapshot or {})["level"] == 1
