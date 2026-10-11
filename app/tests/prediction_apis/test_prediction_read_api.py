from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.predictions import (
    ContributionDirection,
    Disease,
    Prediction,
    PredictionContribution,
    PredictionStatus,
)
from app.services.model_artifact import FACTOR_DICTIONARY_VERSION
from app.tests.d_fixtures import TEST_MODEL_VERSION
from app.tests.prediction_apis.helpers import login, record, serving


async def _prediction(user_id: int, **overrides: Any) -> Prediction:
    health = await record(user_id)
    values: dict[str, Any] = {
        "user_id": user_id,
        "health_record_id": health.id,
        "job_id": f"job-{uuid4().hex}",
        "model_version": TEST_MODEL_VERSION,
        "status": PredictionStatus.PENDING,
    }
    return await Prediction.create(**(values | overrides))


async def _done(user_id: int) -> Prediction:
    """당뇨만 예측된 완료 결과. 고혈압은 진단으로 빠졌다고 본다."""
    prediction = await _prediction(
        user_id,
        status=PredictionStatus.DONE,
        dm_probability=Decimal("0.3125"),
        predicted_at=datetime.now(config.TIMEZONE),
    )
    rows = [("age", "0.05000", 1), ("bmi_high", "0.03000", 2), ("sedentary_time_high", "-0.00100", 3)]
    for factor, value, rank in rows:
        await PredictionContribution.create(
            prediction_id=prediction.id,
            disease=Disease.DIABETES,
            factor_key=factor,
            contribution=Decimal(value),
            direction=ContributionDirection.INCREASE if Decimal(value) > 0 else ContributionDirection.DECREASE,
            rank=rank,
        )
    return prediction


class TestPredictionStatus(TestCase):
    async def test_pending_has_neither_results_nor_failure(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "read-pending@example.com")
                prediction = await _prediction(user.id)
                response = await client.get(f"/api/v1/predictions/{prediction.id}", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == {
            "prediction_id": prediction.id,
            "job_id": prediction.job_id,
            "status": "pending",
            "model_version": TEST_MODEL_VERSION,
            "model_experimental": True,
        }

    async def test_done_lists_only_predicted_diseases(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "read-done@example.com")
                prediction = await _done(user.id)
                response = await client.get(f"/api/v1/predictions/{prediction.id}", headers=headers)

        data = response.json()["data"]
        assert data["status"] == "done"
        assert data["results"] == [{"disease": "diabetes", "probability": 0.3125}]
        assert "failure" not in data

    async def test_failed_carries_failure_without_results(self) -> None:
        failure = {"code": "INTERNAL_ERROR", "message": "예측에 실패했습니다. 다시 시도해주세요.", "retryable": True}
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "read-failed@example.com")
                prediction = await _prediction(user.id, status=PredictionStatus.FAILED, failure=failure)
                response = await client.get(f"/api/v1/predictions/{prediction.id}", headers=headers)

        data = response.json()["data"]
        assert data["status"] == "failed"
        assert data["failure"] == failure
        assert "results" not in data

    async def test_another_users_or_missing_prediction_is_not_found(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                owner, _ = await login(client, "read-owner@example.com")
                _, headers = await login(client, "read-other@example.com")
                prediction = await _done(owner.id)
                theirs = await client.get(f"/api/v1/predictions/{prediction.id}", headers=headers)
                missing = await client.get("/api/v1/predictions/999999", headers=headers)

        for response in (theirs, missing):
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert response.json()["error"]["code"] == "NOT_FOUND"

    async def test_experimental_flag_is_omitted_for_an_older_model_version(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "read-oldver@example.com")
                prediction = await _prediction(user.id, model_version="serving-older")
                response = await client.get(f"/api/v1/predictions/{prediction.id}", headers=headers)

        data = response.json()["data"]
        # 실험 여부를 알 수 없을 때 false 로 채우면 실험 모델이 검증된 모델로 보인다
        assert "model_experimental" not in data
        assert data["model_version"] == "serving-older"

    async def test_non_positive_id_is_a_validation_error(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                _, headers = await login(client, "read-path@example.com")
                response = await client.get("/api/v1/predictions/0", headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestPredictionContributions(TestCase):
    async def _get(self, email: str, query: str = "", *, done: bool = True) -> tuple[Prediction, Any]:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, email)
                prediction = await (_done(user.id) if done else _prediction(user.id))
                response = await client.get(
                    f"/api/v1/predictions/{prediction.id}/contributions{query}", headers=headers
                )
        return prediction, response

    async def test_done_returns_items_by_rank_with_modifiable(self) -> None:
        prediction, response = await self._get("contrib-done@example.com")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["prediction_id"] == prediction.id
        assert data["status"] == "done"
        assert data["model_version"] == TEST_MODEL_VERSION
        assert data["model_experimental"] is True
        assert data["factor_dictionary_version"] == FACTOR_DICTIONARY_VERSION
        assert data["contribution_unit"] == "probability"
        [diabetes] = data["diseases"]
        assert diabetes["disease"] == "diabetes"
        assert [item["factor_key"] for item in diabetes["items"]] == ["age", "bmi_high", "sedentary_time_high"]
        assert [item["rank"] for item in diabetes["items"]] == [1, 2, 3]
        # age 는 바꿀 수 없는 요인이다. 0 이하 기여는 decrease 로 저장돼 있다
        assert [item["modifiable"] for item in diabetes["items"]] == [False, True, True]
        assert diabetes["items"][2]["direction"] == "decrease"
        assert diabetes["items"][2]["contribution"] == -0.001

    async def test_limit_applies_per_disease(self) -> None:
        _, response = await self._get("contrib-limit@example.com", "?limit=2")

        [diabetes] = response.json()["data"]["diseases"]
        assert [item["rank"] for item in diabetes["items"]] == [1, 2]

    async def test_named_disease_returns_a_one_item_array(self) -> None:
        _, response = await self._get("contrib-named@example.com", "?disease=diabetes")

        assert [item["disease"] for item in response.json()["data"]["diseases"]] == ["diabetes"]

    async def test_disease_left_out_of_the_prediction_is_pred_not_found(self) -> None:
        _, response = await self._get("contrib-excluded@example.com", "?disease=hypertension")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["error"]["code"] == "PRED_NOT_FOUND"

    async def test_limit_outside_1_to_100_is_a_validation_error(self) -> None:
        for limit in (0, 101):
            _, response = await self._get(f"contrib-range{limit}@example.com", f"?limit={limit}")

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_pending_omits_diseases(self) -> None:
        _, response = await self._get("contrib-pending@example.com", done=False)

        data = response.json()["data"]
        assert data["status"] == "pending"
        assert "diseases" not in data

    async def test_another_users_prediction_is_not_found(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                owner, _ = await login(client, "contrib-owner@example.com")
                _, headers = await login(client, "contrib-other@example.com")
                prediction = await _done(owner.id)
                response = await client.get(f"/api/v1/predictions/{prediction.id}/contributions", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["error"]["code"] == "NOT_FOUND"
