"""진단자 음주 추천 조건은 승인을 켠 환경에서만 적용한다."""

from datetime import datetime
from unittest.mock import patch

from tortoise.contrib.test import TestCase

from app.core import config
from app.models.challenges import ChallengeRecommendation
from app.models.health_records import HealthRecord
from app.models.users import User
from app.services.impacts import ImpactService
from app.services.recommendations import RecommendationService, behavior_weight
from app.tests.d_fixtures import fake_artifact, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges


def test_alcohol_condition_needs_explicit_enable_and_valid_frequency() -> None:
    def record(frequency: int | None, amount: int | None = None) -> HealthRecord:
        return HealthRecord(
            user_id=1, recorded_at=datetime.now(config.TIMEZONE), alcohol_frequency=frequency, alcohol_amount=amount
        )

    with patch.object(config, "D_DIAGNOSED_ALCOHOL_POLICY_ENABLED", False):
        assert behavior_weight("alcohol_frequency", record(6)) is None
    with patch.object(config, "D_DIAGNOSED_ALCOHOL_POLICY_ENABLED", True):
        assert behavior_weight("alcohol_frequency", record(1)) == 0
        for code in (2, 3, 4, 5, 6):
            assert behavior_weight("alcohol_frequency", record(code)) == 1
        for invalid_code in (None, 0, 7, 8, 9):
            assert behavior_weight("alcohol_frequency", record(invalid_code)) is None
        assert behavior_weight("alcohol_frequency", record(1, 2)) is None
        assert behavior_weight("alcohol_amount", record(6, 5)) is None


class TestAlcoholPolicyIntegration(TestCase):
    async def test_enabled_policy_uses_global_score_without_prediction_or_xp_change(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        user = await User.create(
            email="alcohol-gate@example.com", nickname="검증", password_hash="x", dm_diagnosed=True, htn_diagnosed=True
        )
        target = await make_target(user.id, ["alcohol_frequency"])
        record = await HealthRecord.create(
            user_id=user.id, recorded_at=datetime.now(config.TIMEZONE), alcohol_frequency=2
        )
        artifact = fake_artifact(
            global_scores={"diabetes": {"alcohol_frequency": 40}, "hypertension": {"alcohol_frequency": 30}}
        )
        with patch.object(config, "D_DIAGNOSED_ALCOHOL_POLICY_ENABLED", True):
            result = await RecommendationService(lambda: artifact).generate(user)
            # 음주 빈도 챌린지는 4개이고 한 번에 최대 3장을 낸다. 모두 같은 전역 점수를 쓴다
            assert len(result.items) == 3
            assert {item.factor_score for item in result.items} == {40}
            codes = [result.challenges[item.challenge_id].code for item in result.items]
            assert codes[0] == "CH_NO_DRINK_TODAY"
            assert {result.challenges[item.challenge_id].factor_key for item in result.items} == {"alcohol_frequency"}
            await ImpactService(lambda: artifact).from_health_record(user.id, record.id)
        await user.refresh_from_db()
        await target.refresh_from_db()
        assert user.total_xp == 0 and target.weekly_progress == 0 and target.seal_count == 0
        assert target.impact_score == 40
        assert await ChallengeRecommendation.filter(user_id=user.id).count() == 3
