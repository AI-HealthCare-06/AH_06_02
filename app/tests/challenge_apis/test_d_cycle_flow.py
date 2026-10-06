from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from tortoise.contrib.test import TestCase

from ai_worker.model_contract import threat_from_reference_p95
from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeLog,
    ChallengeRecommendation,
    CooldownChoice,
    OccurrenceStatus,
    RecommendationAction,
    RecommendationSourceType,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
    UserMonster,
    VerificationMethod,
)
from app.models.health_records import HealthRecord
from app.models.predictions import Disease, Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.services.attack_cycles import CYCLE_POLICY_VERSION, AttackCycleService, cycle_week
from app.services.challenges import ChallengeCoreService, xp_for_completion
from app.services.model_artifact import FactorReference, ModelArtifact, personal_threat_score
from app.services.recommendations import RecommendationService, behavior_weight, phase1_candidates
from app.tests.d_fixtures import TEST_MODEL_VERSION, fake_artifact, make_card, make_cycle, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 6, 21, 0, tzinfo=KST)
TODAY = NOW.date()

PHASE1_CODES = {
    # 비세라
    "CH_WALK_AFTER_MEAL",
    "CH_STAND_HOURLY",
    "CH_STAIRS",
    "CH_STRENGTH_10",
    "CH_WALK_ONE_STOP",
    # 소디
    "CH_LEAVE_SOUP",
    "CH_NO_EATING_OUT",
    "CH_HOME_MEAL",
    # 알데
    "CH_NO_DRINK_TODAY",
    # 코티니
    "CH_NO_SMOKE_TODAY",
}


async def _seed() -> dict[str, Challenge]:
    await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
    return {item.code: item for item in await Challenge.all()}


async def _user(email: str, *, dm: bool = False, htn: bool = False) -> User:
    return await User.create(email=email, password_hash="x", nickname="t", dm_diagnosed=dm, htn_diagnosed=htn)


def _service(artifact: ModelArtifact | None) -> RecommendationService:
    return RecommendationService(lambda: artifact)


async def _expect(code: ErrorCode, coro: object) -> None:
    with pytest.raises(AppError) as exc:
        await coro  # type: ignore[misc]
    assert exc.value.code == code


# ---------------------------------------------------------------- 순수 규칙


@pytest.mark.parametrize(
    ("daily_xp", "target", "nth", "expected"),
    [(36, 2, 1, 18), (36, 2, 2, 18), (10, 3, 1, 3), (10, 3, 2, 3), (10, 3, 3, 4), (10, 3, 4, 0), (12, 0, 1, 0)],
)
def test_xp_is_split_and_remainder_goes_to_the_nth_completion(daily_xp: int, target: int, nth: int, expected: int):
    assert xp_for_completion(daily_xp, target, nth) == expected


@pytest.mark.parametrize(
    ("signed", "p95", "eligible"),
    [(0.0064, 0.0128, True), (-0.01, 0.0128, True), (0.5, 0.0128, True), (0.1, 0.2, False)],
)
def test_personal_threat_matches_ai_worker(signed: float, p95: float, eligible: bool) -> None:
    ours = personal_threat_score(signed, FactorReference(positive_shap_p95=p95, threat_eligible=eligible))
    assert ours == threat_from_reference_p95(signed, p95, eligible)


def test_behavior_weight_follows_factor_scales_line_55() -> None:
    record = HealthRecord(user_id=1, recorded_at=NOW, smoking_current=True)
    assert behavior_weight("smoking_current", record) == 1
    assert behavior_weight("smoking_current", HealthRecord(user_id=1, recorded_at=NOW, smoking_current=False)) == 0
    # 누락은 건강한 행동으로 보지 않고 미평가
    assert behavior_weight("smoking_current", HealthRecord(user_id=1, recorded_at=NOW)) is None
    assert behavior_weight("smoking_current", None) is None
    # 비행동 요인은 weight 대상이 아니다
    assert behavior_weight("age", record) == 0
    # 조건 미정 factor 는 건너뛴다
    for factor in ("physical_activity_low", "sedentary_time_high", "alcohol_frequency", "sodium_behavior"):
        assert behavior_weight(factor, record) is None


def test_cycle_week_is_computed_from_d0() -> None:
    cycle = UserAttackCycle(start_date=TODAY)
    assert cycle_week(cycle, TODAY) == 1
    assert cycle_week(cycle, TODAY + timedelta(days=7)) == 2
    assert cycle_week(cycle, TODAY + timedelta(days=27)) == 4
    assert cycle_week(cycle, TODAY + timedelta(days=28)) is None


class TestPhase1Candidates(TestCase):
    async def test_ten_candidates_and_nine_excluded(self) -> None:
        challenges = await _seed()
        candidates = {item.code for item in await phase1_candidates()}

        assert candidates == PHASE1_CODES
        excluded = set(challenges) - candidates
        assert len(excluded) == 9
        assert {"CH_VEGGIE_FIRST", "CH_SLOW_EAT_20"} <= excluded  # 비활성
        assert {"CH_ONE_LESS_GLASS", "CH_WATER_BETWEEN", "CH_DELAY_5MIN"} <= excluded  # 욕구 발생형
        assert {"CH_CHECK_LABEL", "CH_COUNT_DOWN", "CH_WATER_8", "CH_SLEEP_7H"} <= excluded


# ---------------------------------------------------------------- CHLG-01


class TestGenerateRecommendations(TestCase):
    async def test_unavailable_without_artifact(self) -> None:
        user = await _user("r-noart@example.com")
        await _expect(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE, _service(None).generate(user, NOW))

    async def test_unavailable_without_measured_target(self) -> None:
        await _seed()
        user = await _user("r-notarget@example.com")
        await _expect(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE, _service(fake_artifact()).generate(user, NOW))

    async def test_diagnosed_path_uses_global_score_times_weight(self) -> None:
        await _seed()
        user = await _user("r-diag@example.com", dm=True, htn=True)
        await make_target(user.id, ["smoking_current"])
        await HealthRecord.create(user_id=user.id, recorded_at=NOW, smoking_current=True)
        artifact = fake_artifact({"diabetes": {"smoking_current": 40.0}, "hypertension": {"smoking_current": 30.0}})

        result = await _service(artifact).generate(user, NOW)

        assert [result.challenges[item.challenge_id].code for item in result.items] == ["CH_NO_SMOKE_TODAY"]
        card = result.items[0]
        assert card.factor_score == Decimal("40")
        assert card.source_type == RecommendationSourceType.DIAGNOSIS_GLOBAL
        assert result.model_version == TEST_MODEL_VERSION
        # 첫 추천은 기간 없는 draft 주기에 연결한다
        assert result.cycle.status == AttackCycleStatus.DRAFT
        assert result.cycle.start_date is None
        assert result.cycle.policy_version == CYCLE_POLICY_VERSION

    async def test_diagnosed_path_skips_unevaluated_or_pending_factors(self) -> None:
        await _seed()
        smoker_unknown = await _user("r-unknown@example.com", dm=True, htn=True)
        await make_target(smoker_unknown.id, ["smoking_current"])
        await HealthRecord.create(user_id=smoker_unknown.id, recorded_at=NOW)
        pending = await _user("r-pending@example.com", dm=True, htn=True)
        await make_target(pending.id, ["physical_activity_low"])
        await HealthRecord.create(user_id=pending.id, recorded_at=NOW, walking_days=0)
        artifact = fake_artifact(
            {"diabetes": {"smoking_current": 40.0, "physical_activity_low": 20.0}},
        )

        await _expect(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE, _service(artifact).generate(smoker_unknown, NOW))
        await _expect(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE, _service(artifact).generate(pending, NOW))

    async def _prediction(self, user: User, contributions: dict[str, float], model_version: str) -> Prediction:
        record = await HealthRecord.create(user_id=user.id, recorded_at=NOW)
        prediction = await Prediction.create(
            user_id=user.id,
            health_record_id=record.id,
            job_id=f"job-{user.id}",
            model_version=model_version,
            status=PredictionStatus.DONE,
            dm_probability=Decimal("0.3"),
            htn_probability=Decimal("0.2"),
            predicted_at=NOW,
        )
        for disease, value in contributions.items():
            await PredictionContribution.create(
                prediction_id=prediction.id,
                disease=disease,
                factor_key="smoking_current",
                contribution=Decimal(str(value)),
                direction="increase" if value > 0 else "decrease",
                rank=1,
            )
        return prediction

    async def test_personal_path_uses_positive_shap_over_p95(self) -> None:
        await _seed()
        user = await _user("r-personal@example.com")
        await make_target(user.id, ["smoking_current"])
        await self._prediction(user, {"diabetes": 0.0064, "hypertension": 0.002}, TEST_MODEL_VERSION)
        artifact = fake_artifact(
            p95={"diabetes": {"smoking_current": 0.0128}, "hypertension": {"smoking_current": 0.01}}
        )

        result = await _service(artifact).generate(user, NOW)

        card = result.items[0]
        # 당뇨 50, 고혈압 20 중 큰 값
        assert card.factor_score == Decimal("50")
        assert card.source_type == RecommendationSourceType.PREDICTION_PERSONAL

    async def test_both_paths_merge_into_one_card(self) -> None:
        await _seed()
        user = await _user("r-merge@example.com", htn=True)
        await make_target(user.id, ["smoking_current"])
        await self._prediction(user, {"diabetes": 0.0064}, TEST_MODEL_VERSION)
        await HealthRecord.create(user_id=user.id, recorded_at=NOW + timedelta(minutes=1), smoking_current=True)
        artifact = fake_artifact(
            {"hypertension": {"smoking_current": 70.0}}, p95={"diabetes": {"smoking_current": 0.0128}}
        )

        result = await _service(artifact).generate(user, NOW)

        assert len(result.items) == 1
        assert result.items[0].factor_score == Decimal("70")
        assert result.items[0].source_type == RecommendationSourceType.DIAGNOSIS_GLOBAL

    async def test_prediction_from_another_model_version_is_not_reinterpreted(self) -> None:
        await _seed()
        user = await _user("r-version@example.com")
        await make_target(user.id, ["smoking_current"])
        await self._prediction(user, {"diabetes": 0.0064}, "older-model")
        artifact = fake_artifact(p95={"diabetes": {"smoking_current": 0.0128}})

        await _expect(ErrorCode.PRED_NOT_FOUND, _service(artifact).generate(user, NOW))

    async def test_cards_are_ranked_and_capped_at_three(self) -> None:
        await _seed()
        user = await _user("r-rank@example.com")
        await make_target(user.id, ["physical_activity_low", "sedentary_time_high", "strength_activity_low"])
        prediction = await self._prediction(user, {}, TEST_MODEL_VERSION)
        for factor, value in {
            "physical_activity_low": 0.01,
            "sedentary_time_high": 0.004,
            "strength_activity_low": 0.002,
        }.items():
            await PredictionContribution.create(
                prediction_id=prediction.id,
                disease=Disease.DIABETES,
                factor_key=factor,
                contribution=Decimal(str(value)),
                direction="increase",
                rank=1,
            )
        p95 = {"physical_activity_low": 0.01, "sedentary_time_high": 0.01, "strength_activity_low": 0.01}
        artifact = fake_artifact(p95={"diabetes": p95, "hypertension": p95})

        result = await _service(artifact).generate(user, NOW)

        assert [item.rank for item in result.items] == [1, 2, 3]
        assert all(item.factor_key == "physical_activity_low" for item in result.items)


# ---------------------------------------------------------------- CHLG-05


class TestStartInCycle(TestCase):
    async def test_first_start_activates_draft_and_plans_occurrences(self) -> None:
        challenges = await _seed()
        cycle = await make_cycle(1001, ["physical_activity_low"])
        card = await make_card(1001, challenges["CH_WALK_AFTER_MEAL"], cycle)

        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=1001, recommendation_ids=[card.id], now=NOW
        )

        await cycle.refresh_from_db()
        assert cycle.status == AttackCycleStatus.ACTIVE
        assert (cycle.start_date, cycle.end_date) == (TODAY, TODAY + timedelta(days=27))
        assert mission.cycle_id == cycle.id
        assert mission.end_date == cycle.end_date
        assert mission.duration_days_snapshot == 28
        assert mission.goal_config_snapshot == {"difficulty": "challenge", "daily_xp": 36}
        # 점심·저녁 두 슬롯 × 28일
        occurrences = await UserChallengeOccurrence.filter(user_challenge_id=mission.id)
        assert len(occurrences) == 56
        assert {item.slot_code for item in occurrences} == {"lunch", "dinner"}

    async def test_initial_start_is_capped_at_two(self) -> None:
        challenges = await _seed()
        cycle = await make_cycle(1002, ["physical_activity_low", "sedentary_time_high", "strength_activity_low"])
        cards = [
            await make_card(1002, challenges[code], cycle, rank)
            for rank, code in enumerate(["CH_WALK_AFTER_MEAL", "CH_STAND_HOURLY", "CH_STRENGTH_10"], 1)
        ]

        await _expect(
            ErrorCode.CHLG_LIMIT_EXCEEDED,
            ChallengeCoreService().start_from_recommendations(
                user_id=1002, recommendation_ids=[card.id for card in cards], safety_confirmed=True, now=NOW
            ),
        )
        assert await UserChallenge.filter(user_id=1002).count() == 0

    async def test_one_extra_from_week_two(self) -> None:
        challenges = await _seed()
        factors = ["physical_activity_low", "sedentary_time_high", "strength_activity_low"]
        cycle = await make_cycle(1003, factors, start=TODAY - timedelta(days=3))
        service = ChallengeCoreService()
        first = [await make_card(1003, challenges[code], cycle) for code in ("CH_WALK_AFTER_MEAL", "CH_STAND_HOURLY")]
        await service.start_from_recommendations(
            user_id=1003, recommendation_ids=[card.id for card in first], now=NOW - timedelta(days=3)
        )
        extra = await make_card(1003, challenges["CH_STRENGTH_10"], cycle)

        # 1주차에는 초기 2개를 넘길 수 없다
        await _expect(
            ErrorCode.CHLG_LIMIT_EXCEEDED,
            service.start_from_recommendations(
                user_id=1003, recommendation_ids=[extra.id], safety_confirmed=True, now=NOW - timedelta(days=1)
            ),
        )
        # D7 이후 주기당 하나
        [added] = await service.start_from_recommendations(
            user_id=1003, recommendation_ids=[extra.id], safety_confirmed=True, now=NOW + timedelta(days=4)
        )
        await cycle.refresh_from_db()
        assert cycle.extra_added_count == 1
        assert added.end_date == cycle.end_date
        assert added.duration_days_snapshot == 21

    async def test_event_card_needs_confirmed_usage_days(self) -> None:
        challenges = await _seed()
        cycle = await make_cycle(1004, ["physical_activity_low"])
        card = await make_card(1004, challenges["CH_WALK_ONE_STOP"], cycle)

        await _expect(
            ErrorCode.VALIDATION_ERROR,
            ChallengeCoreService().start_from_recommendations(user_id=1004, recommendation_ids=[card.id], now=NOW),
        )

    async def test_card_from_a_past_cycle_cannot_start(self) -> None:
        challenges = await _seed()
        old = await make_cycle(1005, ["smoking_current"], status=AttackCycleStatus.COMPLETED)
        card = await make_card(1005, challenges["CH_NO_SMOKE_TODAY"], old)
        await make_cycle(1005, ["smoking_current"])

        await _expect(
            ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND,
            ChallengeCoreService().start_from_recommendations(user_id=1005, recommendation_ids=[card.id], now=NOW),
        )


# ---------------------------------------------------------------- CHLG-07


class TestRecordLog(TestCase):
    async def _start(self, user_id: int, code: str, factor: str) -> tuple[UserChallenge, UserAttackCycle]:
        challenges = await _seed()
        await User.create(id=user_id, email=f"log{user_id}@example.com", password_hash="x", nickname="t")
        cycle = await make_cycle(user_id, [factor])
        card = await make_card(user_id, challenges[code], cycle)
        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=user_id, recommendation_ids=[card.id], safety_confirmed=True, now=NOW - timedelta(hours=10)
        )
        await cycle.refresh_from_db()
        return mission, cycle

    async def _log(self, mission: UserChallenge, *, slot: str | None = None, value: str | None = None, **kw: object):
        return await ChallengeCoreService().record_log(
            user_id=mission.user_id,
            user_challenge_id=mission.id,
            occurred_at=kw.pop("occurred_at", NOW - timedelta(hours=1)),  # type: ignore[arg-type]
            context_slot=slot,
            value=Decimal(value) if value else None,
            verification_method=kw.pop("method", VerificationMethod.TIMER),  # type: ignore[arg-type]
            evidence_url=None,
            now=kw.pop("now", NOW),  # type: ignore[arg-type]
        )

    async def test_slot_logs_grant_split_xp_and_progress_only(self) -> None:
        mission, cycle = await self._start(2001, "CH_WALK_AFTER_MEAL", "physical_activity_low")
        target = await UserMonster.get(id=cycle.target_user_monster_id)

        lunch = await self._log(mission, slot="lunch", value="10")
        dinner = await self._log(mission, slot="dinner", value="12")

        # 하루 36 XP 를 두 번에 나눠 18씩
        assert (lunch.log.xp_granted, dinner.log.xp_granted) == (18, 18)
        assert (await User.get(id=2001)).total_xp == 36
        assert dinner.weekly_progress == 20
        # 위협도는 수행으로 깎지 않는다 (REQ-CHLG-007)
        await target.refresh_from_db()
        assert target.impact_score == 80
        await _expect(ErrorCode.CHLG_LOG_DUPLICATED, self._log(mission, slot="lunch", value="10"))

    async def test_timer_below_target_fails_and_manual_fallback_is_closed(self) -> None:
        mission, _ = await self._start(2002, "CH_WALK_AFTER_MEAL", "physical_activity_low")

        await _expect(ErrorCode.CHLG_VERIFICATION_FAILED, self._log(mission, slot="lunch", value="9.9"))
        await _expect(
            ErrorCode.CHLG_VERIFICATION_FAILED,
            self._log(mission, slot="lunch", method=VerificationMethod.MANUAL_FALLBACK),
        )
        assert await ChallengeLog.filter(user_challenge_id=mission.id).count() == 0

    async def test_logs_beyond_daily_target_are_kept_without_reward(self) -> None:
        mission, _ = await self._start(2003, "CH_STAND_HOURLY", "sedentary_time_high")

        results = [await self._log(mission, value="3") for _ in range(4)]

        assert [item.log.xp_granted for item in results] == [12, 12, 12, 0]
        assert [item.log.reward_eligible for item in results] == [True, True, True, False]
        assert results[3].weekly_progress is None

    async def test_xp_is_fixed_at_start(self) -> None:
        mission, _ = await self._start(2004, "CH_NO_SMOKE_TODAY", "smoking_current")
        await Challenge.filter(code="CH_NO_SMOKE_TODAY").update(reward_xp=99)

        result = await self._log(mission, method=VerificationMethod.MANUAL)

        assert result.log.xp_granted == 36

    async def test_legacy_mission_without_snapshot_falls_back_to_master(self) -> None:
        mission, _ = await self._start(2005, "CH_NO_SMOKE_TODAY", "smoking_current")
        await UserChallenge.filter(id=mission.id).update(goal_config_snapshot=None)
        await Challenge.filter(code="CH_NO_SMOKE_TODAY").update(reward_xp=24)

        result = await self._log(mission, method=VerificationMethod.MANUAL)

        assert result.log.xp_granted == 24

    async def test_after_d28_logs_are_blocked_and_cycle_closes(self) -> None:
        mission, cycle = await self._start(2006, "CH_NO_SMOKE_TODAY", "smoking_current")
        await self._log(mission, method=VerificationMethod.MANUAL)
        after = NOW + timedelta(days=28)

        await _expect(
            ErrorCode.CHLG_NOT_ACTIVE,
            self._log(mission, method=VerificationMethod.MANUAL, occurred_at=after, now=after),
        )

        await cycle.refresh_from_db()
        await mission.refresh_from_db()
        assert cycle.status == AttackCycleStatus.COMPLETED
        assert mission.status == UserChallengeStatus.GRADUATED
        assert mission.habit_established is None
        assert (mission.completed_occurrence_count, mission.planned_occurrence_count) == (1, 28)
        assert mission.completion_rate == Decimal("0.0357")
        assert mission.summary_policy_version == CYCLE_POLICY_VERSION
        missed = await UserChallengeOccurrence.filter(user_challenge_id=mission.id, status=OccurrenceStatus.MISSED)
        assert len(missed) == 27


# ---------------------------------------------------------------- CHLG-03·04


class TestRejectAndCooldown(TestCase):
    async def test_third_reject_requires_a_cooldown_choice(self) -> None:
        challenges = await _seed()
        user = await _user("cool@example.com")
        cycle = await make_cycle(user.id, ["smoking_current"])
        service = _service(None)
        cards = [await make_card(user.id, challenges["CH_NO_SMOKE_TODAY"], cycle) for _ in range(4)]

        first = await service.act(user, cards[0].id, RecommendationAction.REJECTED, None, NOW)
        await _expect(
            ErrorCode.CHLG_INVALID_COOLDOWN,
            service.act(user, cards[1].id, RecommendationAction.REJECTED, CooldownChoice.DAYS_7, NOW),
        )
        second = await service.act(user, cards[1].id, RecommendationAction.REJECTED, None, NOW)
        await _expect(
            ErrorCode.CHLG_INVALID_COOLDOWN, service.act(user, cards[2].id, RecommendationAction.REJECTED, None, NOW)
        )
        third = await service.act(user, cards[2].id, RecommendationAction.REJECTED, CooldownChoice.UNTIL_MANUAL, NOW)

        assert [first.consecutive_reject_count, second.consecutive_reject_count, third.consecutive_reject_count] == [
            1,
            2,
            3,
        ]
        assert third.suppressed_until_manual is True
        restored = await service.unsuppress(user, third.id)
        assert restored.suppressed_until_manual is False

    async def test_seven_day_cooldown_sets_exclude_until(self) -> None:
        challenges = await _seed()
        user = await _user("cool7@example.com")
        cycle = await make_cycle(user.id, ["smoking_current"])
        service = _service(None)
        for _ in range(2):
            card = await make_card(user.id, challenges["CH_NO_SMOKE_TODAY"], cycle)
            await service.act(user, card.id, RecommendationAction.REJECTED, None, NOW)
        card = await make_card(user.id, challenges["CH_NO_SMOKE_TODAY"], cycle)

        row = await service.act(user, card.id, RecommendationAction.REJECTED, CooldownChoice.DAYS_7, NOW)

        assert row.exclude_until == NOW + timedelta(days=7)

    async def test_cooled_down_challenge_is_not_recommended(self) -> None:
        challenges = await _seed()
        user = await _user("cool-gen@example.com", dm=True, htn=True)
        await make_target(user.id, ["smoking_current"])
        await HealthRecord.create(user_id=user.id, recorded_at=NOW, smoking_current=True)
        await ChallengeRecommendation.create(
            user_id=user.id,
            challenge_id=challenges["CH_NO_SMOKE_TODAY"].id,
            source_type=RecommendationSourceType.DIAGNOSIS_GLOBAL,
            factor_key="smoking_current",
            rank=1,
            recommended_at=NOW,
            action=RecommendationAction.REJECTED,
            suppressed_until_manual=True,
        )
        artifact = fake_artifact({"diabetes": {"smoking_current": 40.0}})

        await _expect(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE, _service(artifact).generate(user, NOW))


# ---------------------------------------------------------------- 종료 집계


class TestCloseExpired(TestCase):
    async def test_cycle_closes_together_at_d28(self) -> None:
        challenges = await _seed()
        start = TODAY - timedelta(days=30)
        cycle = await make_cycle(3001, ["smoking_current"])
        card = await make_card(3001, challenges["CH_NO_SMOKE_TODAY"], cycle)
        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=3001, recommendation_ids=[card.id], now=datetime.combine(start, datetime.min.time(), tzinfo=KST)
        )

        await AttackCycleService().close_expired(3001, TODAY, NOW)

        await mission.refresh_from_db()
        assert mission.status == UserChallengeStatus.GRADUATED
        assert mission.planned_occurrence_count == 28
        assert mission.completed_occurrence_count == 0
        assert mission.completion_rate == Decimal("0")
        assert (await UserAttackCycle.get(id=cycle.id)).status == AttackCycleStatus.COMPLETED

    async def test_completion_rate_is_null_without_planned_occurrences(self) -> None:
        cycle = await make_cycle(3002, ["smoking_current"], start=TODAY - timedelta(days=40))
        mission = await UserChallenge.create(
            user_id=3002,
            challenge_id=1,
            cycle_id=cycle.id,
            start_date=cycle.start_date,
            end_date=cycle.end_date,
            daily_target_count_snapshot=1,
            duration_days_snapshot=28,
        )

        await AttackCycleService().close_expired(3002, TODAY, NOW)

        await mission.refresh_from_db()
        assert mission.planned_occurrence_count == 0
        assert mission.completion_rate is None


def test_policy_version_is_the_agreed_constant() -> None:
    assert CYCLE_POLICY_VERSION == "CYCLE-20261004-v1"
