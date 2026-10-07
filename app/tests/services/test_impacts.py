"""합성 수치는 경계·저장 계약 테스트용이며 학습 산출물이나 임상 기준이 아니다."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from tortoise.contrib.test import TestCase

from app.core.errors import AppError
from app.models.challenges import DefaultImpactSource, ImpactSource, Monster, MonsterState, UserMonster
from app.models.health_records import HealthRecord, InputMode
from app.models.predictions import ContributionDirection, Disease, Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.services.attack_cycles import AttackCycleService
from app.services.impacts import ImpactService, impact_state
from app.services.model_artifact import FactorReference, ModelArtifact
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

NOW = datetime(2026, 10, 7, 12, tzinfo=ZoneInfo("Asia/Seoul"))
VERSION = "unit-test-impact-v1"


def artifact(factors: tuple[str, ...] = ("smoking_current",)) -> ModelArtifact:
    return ModelArtifact(
        model_version=VERSION,
        global_scores={d: dict.fromkeys(factors, 60.0) for d in Disease},
        references={d: {f: FactorReference(0.1, True) for f in factors} for d in Disease},
        experimental=True,
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [(None, "unmeasured"), (0, "not_contributing"), (39, "stable"), (40, "caution"), (69, "caution"), (70, "rage")],
)
def test_game_state_boundaries(score: int | None, expected: str) -> None:
    assert impact_state(score, UserMonster()) == expected


class TestImpactService(TestCase):
    async def setup_data(self, *, diagnosed: bool = False, factors: tuple[str, ...] = ("smoking_current",)):
        user = await User.create(
            email="impact@example.com",
            password_hash="synthetic-test-hash",
            nickname="test",
            dm_diagnosed=diagnosed,
            htn_diagnosed=diagnosed,
        )
        record = await HealthRecord.create(
            user_id=user.id, recorded_at=NOW, smoking_current=True, input_mode=InputMode.SIMPLE
        )
        monster = await Monster.create(code="test-impact", no=1, name="test", factor_keys=list(factors))
        return user, record, monster

    async def prediction(self, user: User, record: HealthRecord, values: dict[str, Decimal], *, version: str = VERSION):
        prediction = await Prediction.create(
            user_id=user.id,
            health_record_id=record.id,
            job_id=f"job-{record.id}-{await Prediction.all().count()}",
            model_version=version,
            status=PredictionStatus.DONE,
            dm_probability=Decimal("0.1"),
            htn_probability=Decimal("0.2"),
            predicted_at=NOW,
        )
        for disease in Disease:
            for rank, (factor, value) in enumerate(values.items(), 1):
                await PredictionContribution.create(
                    prediction_id=prediction.id,
                    disease=disease,
                    factor_key=factor,
                    contribution=value,
                    direction=ContributionDirection.INCREASE if value > 0 else ContributionDirection.DECREASE,
                    rank=rank,
                )
        return prediction

    async def test_same_record_prediction_updates_and_allows_target_selection(self):
        user, record, monster = await self.setup_data()
        prediction = await self.prediction(user, record, {"smoking_current": Decimal("0.08")})
        result = await ImpactService(lambda: artifact()).from_prediction(user.id, prediction.id)
        row = await UserMonster.get(user_id=user.id, monster_id=monster.id)
        assert result == {"updated": 1, "sealed": []}
        assert (row.impact_score, row.state, row.impact_source) == (80, MonsterState.RAGE, ImpactSource.CONTRIBUTION)
        assert row.last_prediction_id == prediction.id
        target = await AttackCycleService().select_target(user.id)
        assert target is not None and target.id == row.id

    async def test_negative_shap_is_zero_not_absolute_value(self):
        user, record, monster = await self.setup_data()
        prediction = await self.prediction(user, record, {"smoking_current": Decimal("-0.08")})
        await ImpactService(lambda: artifact()).from_prediction(user.id, prediction.id)
        row = await UserMonster.get(user_id=user.id, monster_id=monster.id)
        assert row.impact_score == 0 and row.state == MonsterState.NOT_CONTRIBUTING

    async def test_health_save_waits_for_personal_shap_and_does_not_reuse_other_record(self):
        user, record, monster = await self.setup_data()
        previous = await self.prediction(user, record, {"smoking_current": Decimal("0.08")})
        service = ImpactService(lambda: artifact())
        await service.from_prediction(user.id, previous.id)
        newer = await HealthRecord.create(user_id=user.id, recorded_at=NOW + timedelta(hours=1), smoking_current=False)
        assert await service.from_health_record(user.id, newer.id) == {"updated": 0, "sealed": []}
        row = await UserMonster.get(user_id=user.id, monster_id=monster.id)
        assert row.last_health_record_id == record.id and row.impact_score == 80

    async def test_old_record_wrong_version_and_pending_jobs_cannot_overwrite(self):
        user, record, _ = await self.setup_data()
        service = ImpactService(lambda: artifact())
        wrong = await self.prediction(user, record, {"smoking_current": Decimal("0.08")}, version="wrong")
        assert (await service.from_prediction(user.id, wrong.id))["updated"] == 0
        wrong.model_version, wrong.status = VERSION, PredictionStatus.PENDING
        await wrong.save()
        assert (await service.from_prediction(user.id, wrong.id))["updated"] == 0
        wrong.status = PredictionStatus.DONE
        await wrong.save()
        await HealthRecord.create(user_id=user.id, recorded_at=NOW + timedelta(hours=1))
        assert (await service.from_prediction(user.id, wrong.id))["updated"] == 0
        assert await UserMonster.all().count() == 0

    async def test_daily_records_do_not_invalidate_the_non_daily_input(self):
        user, record, _ = await self.setup_data()
        prediction = await self.prediction(user, record, {"smoking_current": Decimal("0.05")})
        daily = await HealthRecord.create(
            user_id=user.id, recorded_at=NOW + timedelta(hours=1), input_mode=InputMode.DAILY
        )
        service = ImpactService(lambda: artifact())
        assert (await service.from_health_record(user.id, daily.id))["updated"] == 0
        assert (await service.from_prediction(user.id, prediction.id))["updated"] == 1

    async def test_missing_contribution_is_not_healthy_zero(self):
        user, record, _ = await self.setup_data()
        prediction = await self.prediction(user, record, {})
        assert (await ImpactService(lambda: artifact()).from_prediction(user.id, prediction.id))["updated"] == 0
        assert await UserMonster.all().count() == 0

    async def test_monster_uses_maximum_factor_not_sum(self):
        factors = ("physical_activity_low", "strength_activity_low")
        user, record, monster = await self.setup_data(factors=factors)
        prediction = await self.prediction(user, record, {factors[0]: Decimal("0.04"), factors[1]: Decimal("0.06")})
        await ImpactService(lambda: artifact(factors)).from_prediction(user.id, prediction.id)
        assert (await UserMonster.get(user_id=user.id, monster_id=monster.id)).impact_score == 60

    async def test_diagnosed_smoker_uses_approved_binary_weight_without_prediction(self):
        user, record, monster = await self.setup_data(diagnosed=True)
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        assert (await ImpactService(lambda: artifact()).from_health_record(user.id, record.id))["updated"] == 1
        row = await UserMonster.get(user_id=user.id, monster_id=monster.id)
        assert row.impact_score == 60 and row.impact_source == ImpactSource.GLOBAL
        assert row.last_prediction_id is None

    async def test_pending_diagnosed_cutoff_is_not_invented(self):
        factors = ("physical_activity_low",)
        user, record, _ = await self.setup_data(diagnosed=True, factors=factors)
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        assert (await ImpactService(lambda: artifact(factors)).from_health_record(user.id, record.id))["updated"] == 0

    async def test_unconfigured_spike_remains_unmeasured(self):
        user, record, monster = await self.setup_data()
        monster.default_impact_source = DefaultImpactSource.MEASURED
        await monster.save()
        assert (await ImpactService(lambda: artifact()).from_health_record(user.id, record.id))["updated"] == 0
        assert await UserMonster.all().count() == 0

    async def test_existing_seal_progress_and_user_xp_are_preserved(self):
        user, record, monster = await self.setup_data()
        sealed = await UserMonster.create(
            user_id=user.id,
            monster_id=monster.id,
            state=MonsterState.SEALED,
            impact_score=20,
            sealed_at=NOW - timedelta(days=1),
            seal_count=1,
            weekly_progress=42,
        )
        prediction = await self.prediction(user, record, {"smoking_current": Decimal("0.08")})
        await ImpactService(lambda: artifact()).from_prediction(user.id, prediction.id)
        await sealed.refresh_from_db()
        await user.refresh_from_db()
        assert sealed.state == MonsterState.SEALED and sealed.seal_count == 1
        assert sealed.sealed_at is not None and sealed.reawakened_at is not None
        assert sealed.weekly_progress == 42 and user.total_xp == 0

    async def test_zero_after_positive_is_resolved_and_keeps_first_resolution_time(self):
        user, record, monster = await self.setup_data()
        service = ImpactService(lambda: artifact())
        first = await self.prediction(user, record, {"smoking_current": Decimal("0.08")})
        await service.from_prediction(user.id, first.id)
        second = await self.prediction(user, record, {"smoking_current": Decimal("0")})
        await service.from_prediction(user.id, second.id)
        row = await UserMonster.get(user_id=user.id, monster_id=monster.id)
        timestamp = row.resolved_at
        assert row.state == MonsterState.RESOLVED and timestamp is not None
        await service.from_prediction(user.id, second.id)
        await row.refresh_from_db()
        assert row.resolved_at == timestamp

    async def test_foreign_prediction_is_rejected_without_monster_writes(self):
        user, record, _ = await self.setup_data()
        prediction = await self.prediction(user, record, {"smoking_current": Decimal("0.05")})
        with pytest.raises(AppError):
            await ImpactService(lambda: artifact()).from_prediction(user.id + 1, prediction.id)
        assert await UserMonster.all().count() == 0
