from datetime import datetime

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.predictions import Prediction, PredictionStatus
from app.models.users import User
from app.tests.d_fixtures import TEST_MODEL_VERSION, fake_artifact
from app.tests.prediction_apis.helpers import RecordingQueue, login, record, serving, snapshot

URL = "/api/v1/predictions"


class TestCreatePrediction(TestCase):
    async def test_accepts_and_stores_a_pending_prediction(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-ok@example.com")
                health = await record(user.id)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()["data"]
        assert set(data) == {"prediction_id", "job_id", "status", "model_version", "model_experimental", "poll_url"}
        assert data["status"] == "pending"
        assert data["model_version"] == TEST_MODEL_VERSION
        assert data["model_experimental"] is True
        assert data["poll_url"] == f"/api/v1/predictions/{data['prediction_id']}"
        saved = await Prediction.get(id=data["prediction_id"])
        assert (saved.user_id, saved.health_record_id, saved.status) == (user.id, health.id, PredictionStatus.PENDING)
        assert saved.job_id == data["job_id"]
        assert saved.model_version == TEST_MODEL_VERSION
        # 나이는 접수 시점의 출생연도로 고정한다 (가입 본문 1998)
        assert snapshot(saved)["features"]["age"] == datetime.now(config.TIMEZONE).year - 1998
        assert snapshot(saved)["diseases"] == ["diabetes", "hypertension"]

    async def test_enqueues_only_ids_for_the_worker(self) -> None:
        queue = RecordingQueue()
        with serving(queue=queue):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-queue@example.com")
                health = await record(user.id)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        data = response.json()["data"]
        assert queue.jobs == [(data["prediction_id"], data["job_id"])]

    async def test_queue_failure_marks_failed_instead_of_permanent_pending(self) -> None:
        with serving(queue=RecordingQueue(fail=True)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-queue-down@example.com")
                health = await record(user.id)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        saved = await Prediction.get(user_id=user.id)
        assert saved.status == PredictionStatus.FAILED
        assert saved.failure == {
            "code": "INTERNAL_ERROR",
            "message": "예측에 실패했습니다. 다시 시도해주세요.",
            "retryable": True,
        }

    async def test_another_users_record_is_not_found(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                owner, _ = await login(client, "pred-owner@example.com")
                _, headers = await login(client, "pred-other@example.com")
                health = await record(owner.id)
                theirs = await client.post(URL, json={"health_record_id": health.id}, headers=headers)
                missing = await client.post(URL, json={"health_record_id": 999999}, headers=headers)

        for response in (theirs, missing):
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert response.json()["error"]["code"] == "HLTH_RECORD_NOT_FOUND"
        assert await Prediction.all().count() == 0

    async def test_both_diseases_diagnosed_or_medicated_is_rejected(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-both@example.com", dm_medication=True, htn_diagnosed=True)
                health = await record(user.id)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "PRED_ALL_DIAGNOSED"
        assert await Prediction.all().count() == 0

    async def test_a_diagnosed_disease_drops_out_with_its_features(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-one@example.com", dm_diagnosed=True)
                # 좌식시간은 당뇨 모델만 쓴다. 당뇨가 빠지면 없어도 접수된다
                health = await record(user.id, sitting_minutes=None)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_202_ACCEPTED
        saved = await Prediction.get(id=response.json()["data"]["prediction_id"])
        assert snapshot(saved)["diseases"] == ["hypertension"]
        assert "sitting_minutes" not in snapshot(saved)["features"]

    async def test_missing_birth_year_or_sex_is_profile_incomplete(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-profile@example.com")
                await User.filter(id=user.id).update(sex=None)
                health = await record(user.id)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "HLTH_PROFILE_INCOMPLETE"

    async def test_missing_model_inputs_are_all_listed(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-missing@example.com")
                health = await record(user.id, waist_cm=None, sitting_minutes=None)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error = response.json()["error"]
        assert error["code"] == "PRED_INPUT_INSUFFICIENT"
        assert "waist_cm" in error["message"]
        assert "sitting_minutes" in error["message"]
        assert await Prediction.all().count() == 0

    async def test_non_drinker_amount_is_zero_but_drinker_amount_is_required(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-alcohol@example.com")
                non_drinker = await record(user.id, alcohol_frequency=1, alcohol_amount=None)
                drinker = await record(user.id, alcohol_frequency=3, alcohol_amount=None)
                accepted = await client.post(URL, json={"health_record_id": non_drinker.id}, headers=headers)
                rejected = await client.post(URL, json={"health_record_id": drinker.id}, headers=headers)

        assert accepted.status_code == status.HTTP_202_ACCEPTED
        saved = await Prediction.get(id=accepted.json()["data"]["prediction_id"])
        assert snapshot(saved)["features"]["alcohol_amount"] == 0
        assert rejected.json()["error"]["code"] == "PRED_INPUT_INSUFFICIENT"
        assert "alcohol_amount" in rejected.json()["error"]["message"]

    async def test_zero_walking_days_means_zero_walking_minutes(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-walk@example.com")
                health = await record(user.id, walking_days=0, walking_minutes=None)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_202_ACCEPTED
        saved = await Prediction.get(id=response.json()["data"]["prediction_id"])
        assert snapshot(saved)["features"]["walking_minutes"] == 0

    async def test_no_active_artifact_is_an_internal_error(self) -> None:
        with serving(None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-noart@example.com")
                health = await record(user.id)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert await Prediction.all().count() == 0

    async def test_artifact_without_model_input_list_is_an_internal_error(self) -> None:
        # features 를 싣기 전에 만든 옛 아티팩트. 필수 입력을 정할 수 없어 접수하지 않는다
        with serving(fake_artifact()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login(client, "pred-nofeatures@example.com")
                health = await record(user.id)
                response = await client.post(URL, json={"health_record_id": health.id}, headers=headers)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert await Prediction.all().count() == 0

    async def test_malformed_body_is_a_validation_error(self) -> None:
        with serving():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                _, headers = await login(client, "pred-body@example.com")
                zero = await client.post(URL, json={"health_record_id": 0}, headers=headers)
                empty = await client.post(URL, json={}, headers=headers)

        for response in (zero, empty):
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
