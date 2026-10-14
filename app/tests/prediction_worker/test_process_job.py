"""ai_worker 저장 계약. 모델은 흉내 내고 DB 반영·멱등·실패 기록만 본다 (app 의존성만으로 돈다)."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from ai_worker.tasks.inference import ModelUnavailableError, ServingModels
from ai_worker.tasks.predict import MODEL_FAILURE, RETRY_FAILURE, process_job
from app.core import config
from app.main import app
from app.models.predictions import Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.tests.d_fixtures import TEST_MODEL_VERSION
from app.tests.prediction_apis.helpers import login, record

SNAPSHOT_FEATURES = {
    "age": 20,
    "sex": "F",
    "bmi": 23.1,
    "waist_cm": 80.0,
    "smoking_current": 0,
    "alcohol_frequency": 3,
    "alcohol_amount": 2,
    "walking_days": 2,
    "walking_minutes": 20,
    "strength_days": 1,
    "family_history_dm": 1,
    "family_history_htn": 0,
    "sitting_minutes": 540,
    "dining_out_freq": 3,
}


def contributions(*factors: str) -> list[dict[str, Any]]:
    return [
        {"factor_key": key, "contribution": 0.01 * (len(factors) - rank), "direction": "increase", "rank": rank + 1}
        for rank, key in enumerate(factors)
    ]


class StubModel:
    def __init__(self, probability: float, factors: tuple[str, ...], fail: bool = False) -> None:
        self.probability = probability
        self.factors = factors
        self.fail = fail
        self.seen: list[dict[str, Any]] = []

    def predict(self, features: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
        self.seen.append(features)
        if self.fail:
            raise ValueError("boom")
        return self.probability, contributions(*self.factors)


def models(**diseases: StubModel) -> ServingModels:
    return ServingModels(model_version=TEST_MODEL_VERSION, diseases=diseases)  # type: ignore[arg-type]


async def pending(email: str, diseases: list[str]) -> tuple[User, Prediction]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        user, _ = await login(client, email)
    health = await record(user.id, weight_kg=Decimal("62.0"))
    prediction = await Prediction.create(
        user_id=user.id,
        health_record_id=health.id,
        job_id=f"job-{uuid4().hex}",
        model_version=TEST_MODEL_VERSION,
        input_snapshot={"diseases": diseases, "features": SNAPSHOT_FEATURES},
    )
    return user, prediction


def job(prediction: Prediction) -> dict[str, Any]:
    return {"prediction_id": prediction.id, "job_id": prediction.job_id}


@patch("app.services.impacts.refresh_impact_from_prediction", new_callable=AsyncMock)
class TestProcessJob(TestCase):
    async def test_done_stores_both_diseases_and_all_factors_once(self, refresh: AsyncMock) -> None:
        user, prediction = await pending("worker-done@example.com", ["diabetes", "hypertension"])
        dm = StubModel(0.312345, ("age", "bmi_high", "sedentary_time_high"))
        htn = StubModel(0.2, ("age", "sodium_behavior"))

        outcome = await process_job(job(prediction), models(diabetes=dm, hypertension=htn))
        # 같은 job 재전달은 결과·기여도를 다시 만들지 않는다
        again = await process_job(job(prediction), models(diabetes=dm, hypertension=htn))

        assert outcome is not None and outcome.status == PredictionStatus.DONE
        assert again is None
        saved = await Prediction.get(id=prediction.id)
        assert saved.status == PredictionStatus.DONE
        assert (saved.dm_probability, saved.htn_probability) == (Decimal("0.3123"), Decimal("0.2000"))
        assert saved.dm_grade is None and saved.failure is None and saved.predicted_at is not None
        rows = await PredictionContribution.filter(prediction_id=prediction.id).order_by("disease", "rank")
        assert [(row.disease, row.factor_key, row.rank) for row in rows] == [
            ("diabetes", "age", 1),
            ("diabetes", "bmi_high", 2),
            ("diabetes", "sedentary_time_high", 3),
            ("hypertension", "age", 1),
            ("hypertension", "sodium_behavior", 2),
        ]
        refresh.assert_awaited_once_with(user.id, prediction.id)

    async def test_worker_computes_bmi_and_age_from_users_and_health_record(self, refresh: AsyncMock) -> None:
        user, prediction = await pending("worker-bmi@example.com", ["diabetes"])
        dm = StubModel(0.1, ("age",))

        await process_job(job(prediction), models(diabetes=dm))

        height = float(user.height_cm) / 100  # type: ignore[arg-type]
        seen = dm.seen[0]
        # 반올림한 health_records.bmi(23.1) 가 아니라 체중·키로 다시 계산한 값이다
        assert seen["bmi"] == 62.0 / (height * height)
        assert seen["age"] == datetime.now(config.TIMEZONE).year - user.birth_year  # type: ignore[operator]
        assert seen["sex"] == "F" and seen["smoking_current"] == 0

    async def test_diagnosed_disease_is_not_predicted(self, refresh: AsyncMock) -> None:
        _, prediction = await pending("worker-one@example.com", ["hypertension"])
        dm = StubModel(0.9, ("age",))

        await process_job(job(prediction), models(diabetes=dm, hypertension=StubModel(0.2, ("age",))))

        saved = await Prediction.get(id=prediction.id)
        assert saved.dm_probability is None and saved.htn_probability == Decimal("0.2000")
        assert dm.seen == []

    async def test_one_disease_failure_publishes_no_partial_result(self, refresh: AsyncMock) -> None:
        _, prediction = await pending("worker-partial@example.com", ["diabetes", "hypertension"])

        await process_job(
            job(prediction),
            models(diabetes=StubModel(0.3, ("age",)), hypertension=StubModel(0.2, ("age",), fail=True)),
        )

        saved = await Prediction.get(id=prediction.id)
        assert saved.status == PredictionStatus.FAILED and saved.failure == RETRY_FAILURE
        assert saved.dm_probability is None
        assert await PredictionContribution.filter(prediction_id=prediction.id).count() == 0
        refresh.assert_not_awaited()

    async def test_missing_model_is_a_non_retryable_failure(self, refresh: AsyncMock) -> None:
        _, prediction = await pending("worker-nomodel@example.com", ["diabetes"])

        await process_job(job(prediction), ModelUnavailableError("background-diabetes.npy 없음"))

        saved = await Prediction.get(id=prediction.id)
        assert saved.status == PredictionStatus.FAILED and saved.failure == MODEL_FAILURE

    async def test_model_changed_since_submission_fails(self, refresh: AsyncMock) -> None:
        _, prediction = await pending("worker-version@example.com", ["diabetes"])
        other = ServingModels(model_version="serving-other", diseases={"diabetes": StubModel(0.1, ("age",))})  # type: ignore[dict-item]

        await process_job(job(prediction), other)

        saved = await Prediction.get(id=prediction.id)
        assert saved.status == PredictionStatus.FAILED and saved.failure == MODEL_FAILURE

    async def test_mismatched_job_or_finished_prediction_is_ignored(self, refresh: AsyncMock) -> None:
        _, prediction = await pending("worker-ignore@example.com", ["diabetes"])
        dm = StubModel(0.1, ("age",))

        assert await process_job({"prediction_id": prediction.id, "job_id": "job-other"}, models(diabetes=dm)) is None
        assert await process_job({"prediction_id": "1", "job_id": prediction.job_id}, models(diabetes=dm)) is None
        await Prediction.filter(id=prediction.id).update(status=PredictionStatus.FAILED)
        assert await process_job(job(prediction), models(diabetes=dm)) is None
        assert dm.seen == []
