"""다음 주기 추천이 지난 주기 수행률로 개인 목표 단계를 정하는지 확인한다.

80% 이상 한 단계 위, 50% 이상 80% 미만 유지, 50% 미만 한 단계 아래.
가장 낮은 단계에서 50% 미만이면 다른 챌린지를 먼저 추천한다. 놓친 날로 점수를 깎지는 않는다.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from tortoise.contrib.test import TestCase

from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    UserAttackCycle,
    UserChallenge,
    UserChallengeStatus,
    UserMonster,
)
from app.models.health_records import HealthRecord
from app.models.predictions import Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.services.attack_cycles import CYCLE_POLICY_VERSION
from app.services.challenge_goals import goal_policy
from app.services.recommendations import GeneratedRecommendations, RecommendationService
from app.tests.d_fixtures import TEST_MODEL_VERSION, fake_artifact, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 27, 21, 0, tzinfo=KST)
TODAY = NOW.date()
DELAY = "CH_DELAY_FIRST_CIG"


class TestPersonalGoalProgression(TestCase):
    async def _ready(self, email: str, codes: tuple[str, ...] = (DELAY,)) -> tuple[User, UserMonster]:
        """흡연 요인 카드는 codes 만 남기고, 고혈압 진단 경로로 점수를 낸다."""
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        await Challenge.filter(factor_key="smoking_current").exclude(code__in=codes).update(is_enabled=False)
        user = await User.create(email=email, password_hash="x", nickname="t", htn_diagnosed=True)
        target = await make_target(user.id, ["smoking_current"])
        record = await HealthRecord.create(user_id=user.id, recorded_at=NOW, smoking_current=True)
        prediction = await Prediction.create(
            user_id=user.id,
            health_record_id=record.id,
            job_id=f"job-{user.id}",
            model_version=TEST_MODEL_VERSION,
            status=PredictionStatus.DONE,
            dm_probability=Decimal("0.3"),
            predicted_at=NOW,
        )
        await PredictionContribution.create(
            prediction_id=prediction.id,
            disease="diabetes",
            factor_key="smoking_current",
            contribution=Decimal("0.0064"),
            direction="increase",
            rank=1,
        )
        return user, target

    async def _finished(
        self, user: User, target: UserMonster, rate: str | None, level: int, code: str = DELAY
    ) -> UserChallenge:
        """지난 주기에 기간 종료로 끝난 미션."""
        challenge = await Challenge.get(code=code)
        policy = goal_policy(challenge)
        start = TODAY - timedelta(days=30)
        cycle = await UserAttackCycle.create(
            user_id=user.id,
            target_user_monster_id=target.id,
            status=AttackCycleStatus.COMPLETED,
            policy_version=CYCLE_POLICY_VERSION,
            start_date=start,
            end_date=start + timedelta(days=27),
        )
        return await UserChallenge.create(
            user_id=user.id,
            challenge_id=challenge.id,
            cycle_id=cycle.id,
            status=UserChallengeStatus.GRADUATED,
            start_date=start,
            end_date=start + timedelta(days=27),
            daily_target_count_snapshot=1,
            duration_days_snapshot=28,
            completion_rate=None if rate is None else Decimal(rate),
            goal_config_snapshot={"level": level, "policy_version": policy.version if policy else None},
        )

    async def _generate(self, user: User) -> GeneratedRecommendations:
        artifact = fake_artifact(
            {"hypertension": {"smoking_current": 70.0}}, p95={"diabetes": {"smoking_current": 0.0128}}
        )
        return await RecommendationService(lambda: artifact).generate(user, NOW)

    async def _goal_for(self, user: User, code: str = DELAY) -> dict[str, Any] | None:
        result = await self._generate(user)
        challenge = await Challenge.get(code=code)
        [card] = [item for item in result.items if item.challenge_id == challenge.id]
        return card.proposed_goal

    async def test_high_completion_moves_one_step_up(self) -> None:
        user, target = await self._ready("p-up@example.com")
        mission = await self._finished(user, target, "0.8000", level=2)

        goal = await self._goal_for(user)

        assert goal is not None
        assert goal["level"] == 3
        assert goal["basis"] == {
            "user_challenge_id": mission.id,
            "completion_rate": "0.8000",
            "previous_level": 2,
            "direction": "up",
        }

    async def test_middle_completion_keeps_the_step(self) -> None:
        user, target = await self._ready("p-keep@example.com")
        await self._finished(user, target, "0.7999", level=2)

        goal = await self._goal_for(user)

        assert goal is not None
        assert (goal["level"], goal["basis"]["direction"]) == (2, "keep")

    async def test_low_completion_moves_one_step_down(self) -> None:
        user, target = await self._ready("p-down@example.com")
        await self._finished(user, target, "0.4999", level=2)

        goal = await self._goal_for(user)

        assert goal is not None
        assert (goal["level"], goal["basis"]["direction"]) == (1, "down")

    async def test_half_completion_is_kept_not_lowered(self) -> None:
        user, target = await self._ready("p-half@example.com")
        await self._finished(user, target, "0.5000", level=2)

        goal = await self._goal_for(user)

        assert goal is not None
        assert goal["level"] == 2

    async def test_top_step_stays_at_the_top(self) -> None:
        user, target = await self._ready("p-top@example.com")
        await self._finished(user, target, "1.0000", level=3)

        goal = await self._goal_for(user)

        assert goal is not None
        assert (goal["level"], goal["basis"]["direction"]) == (3, "keep")

    async def test_low_completion_at_the_lowest_step_suggests_another_challenge_first(self) -> None:
        other = "CH_SMOKE_FREE_HOME"
        user, target = await self._ready("p-other@example.com", codes=(DELAY, other))
        await self._finished(user, target, "0.2000", level=1)

        result = await self._generate(user)

        delay = await Challenge.get(code=DELAY)
        ranks = {item.challenge_id: item.rank for item in result.items}
        # 평소에는 등록 순서가 빠른 미루기가 먼저다
        assert ranks[(await Challenge.get(code=other)).id] == 1
        assert ranks[delay.id] == 2
        [card] = [item for item in result.items if item.challenge_id == delay.id]
        assert card.proposed_goal is not None
        assert card.proposed_goal["level"] == 1

    async def test_mission_without_completion_rate_is_not_used(self) -> None:
        user, target = await self._ready("p-null@example.com")
        await self._finished(user, target, None, level=1)

        assert await self._goal_for(user) is None

    async def test_challenge_without_policy_stays_on_the_fixed_goal(self) -> None:
        code = "CH_SMOKE_FREE_HOME"
        user, target = await self._ready("p-fixed@example.com", codes=(code,))
        await self._finished(user, target, "0.9000", level=1, code=code)

        assert await self._goal_for(user, code) is None

    async def test_restart_in_the_same_cycle_proposes_the_first_step(self) -> None:
        user, target = await self._ready("p-restart@example.com")
        delay = await Challenge.get(code=DELAY)
        policy = goal_policy(delay)
        assert policy is not None
        cycle = await UserAttackCycle.create(
            user_id=user.id,
            target_user_monster_id=target.id,
            status=AttackCycleStatus.ACTIVE,
            policy_version=CYCLE_POLICY_VERSION,
            start_date=TODAY,
            end_date=TODAY + timedelta(days=27),
        )
        basis = {"user_challenge_id": 1, "completion_rate": "0.3000", "previous_level": 2, "direction": "down"}
        await UserChallenge.create(
            user_id=user.id,
            challenge_id=delay.id,
            cycle_id=cycle.id,
            status=UserChallengeStatus.ABANDONED,
            start_date=TODAY,
            end_date=TODAY + timedelta(days=27),
            daily_target_count_snapshot=1,
            duration_days_snapshot=28,
            goal_config_snapshot={"level": 1, "policy_version": policy.version, "basis": basis},
        )

        goal = await self._goal_for(user)

        assert goal == {"policy_version": policy.version, "level": 1, "basis": basis}

    async def test_card_shows_the_step_goal_and_why_it_changed(self) -> None:
        user, target = await self._ready("p-body@example.com")
        await self._finished(user, target, "0.9000", level=2)
        await self._generate(user)

        [item], _ = await RecommendationService().list_cards(user, 1, 10)

        assert item["title"] == "아침 첫 담배 1시간 미루기"
        assert (item["difficulty"], item["daily_xp"], item["goal_level"]) == ("challenge", 36, 3)
        assert item["goal_basis"]["direction"] == "up"
        # 한 단계 올린 목표라 화면이 시작 전 안전 확인을 띄우게 한다
        assert item["safety_check_required"] is True
