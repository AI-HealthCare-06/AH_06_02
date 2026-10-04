from decimal import Decimal

import pytest
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError

from app.models.predictions import (
    ContributionDirection,
    Disease,
    Prediction,
    PredictionContribution,
    PredictionStatus,
    RiskGrade,
)


async def _create_prediction(job_id: str = "job-1") -> Prediction:
    return await Prediction.create(
        user_id=1,
        health_record_id=1,
        job_id=job_id,
        model_version="knhanes-ix-diabetes-base_sitting-s42",
    )


class TestPredictionModel(TestCase):
    async def test_defaults_follow_the_spec(self):
        prediction = await _create_prediction()

        # 접수 직후에는 추론 전이라 확률과 등급이 비어 있다 (REQ-PRED-002)
        assert prediction.status == PredictionStatus.PENDING
        assert prediction.dm_probability is None
        assert prediction.dm_grade is None
        assert prediction.predicted_at is None

    async def test_job_id_is_unique(self):
        await _create_prediction(job_id="job-dup")

        with pytest.raises(IntegrityError):
            await _create_prediction(job_id="job-dup")

    async def test_probability_keeps_four_decimal_places(self):
        prediction = await _create_prediction(job_id="job-prob")
        prediction.dm_probability = Decimal("0.7325")
        prediction.dm_grade = RiskGrade.CAUTION
        await prediction.save()

        reloaded = await Prediction.get(id=prediction.id)
        # 확률은 0~1로 저장하고 화면에서만 %로 바꾼다
        assert reloaded.dm_probability == Decimal("0.7325")
        assert reloaded.dm_grade == RiskGrade.CAUTION


class TestPredictionContributionModel(TestCase):
    async def test_contributions_are_stored_per_disease(self):
        prediction = await _create_prediction(job_id="job-contrib")

        await PredictionContribution.create(
            prediction_id=prediction.id,
            disease=Disease.DIABETES,
            factor_key="bmi_high",
            contribution=Decimal("0.12345"),
            direction=ContributionDirection.INCREASE,
            rank=1,
        )
        await PredictionContribution.create(
            prediction_id=prediction.id,
            disease=Disease.HYPERTENSION,
            factor_key="sodium_behavior",
            contribution=Decimal("-0.02000"),
            direction=ContributionDirection.DECREASE,
            rank=1,
        )

        rows = await PredictionContribution.filter(prediction_id=prediction.id).order_by("disease", "rank")
        assert [row.disease for row in rows] == [Disease.DIABETES, Disease.HYPERTENSION]
        assert rows[0].contribution == Decimal("0.12345")

    async def test_zero_contribution_is_recorded_as_decrease(self):
        prediction = await _create_prediction(job_id="job-zero")

        # 0은 ENUM 제약에 따라 decrease로 적는다. 보호 효과를 뜻하지는 않는다
        row = await PredictionContribution.create(
            prediction_id=prediction.id,
            disease=Disease.DIABETES,
            factor_key="family_history_dm",
            contribution=Decimal("0.00000"),
            direction=ContributionDirection.DECREASE,
            rank=9,
        )

        assert row.direction == ContributionDirection.DECREASE
