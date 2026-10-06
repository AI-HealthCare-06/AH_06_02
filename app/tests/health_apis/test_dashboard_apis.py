from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.health_records import HealthRecord
from app.models.predictions import Prediction, PredictionStatus
from app.models.users import User
from app.tests.auth_apis.test_signup_api import signup_body

PASSWORD = "dango1234"


async def _login(client: AsyncClient, email: str) -> tuple[str, User]:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email))
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return str(res.json()["data"]["access_token"]), await User.get(email=email)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _record(user: User, days_ago: int, **values: Any) -> HealthRecord:
    recorded_at = datetime.now(config.TIMEZONE) - timedelta(days=days_ago)
    return await HealthRecord.create(user_id=user.id, recorded_at=recorded_at, **values)


async def _prediction(
    user: User,
    record: HealthRecord,
    *,
    dm: str | None,
    htn: str | None,
    status_: PredictionStatus = PredictionStatus.DONE,
) -> Prediction:
    return await Prediction.create(
        user_id=user.id,
        health_record_id=record.id,
        job_id=f"job-{uuid4().hex}",
        model_version="test-model",
        status=status_,
        dm_probability=Decimal(dm) if dm else None,
        htn_probability=Decimal(htn) if htn else None,
        predicted_at=record.recorded_at + timedelta(minutes=1),
    )


class TestDashboardSummaryAPI(TestCase):
    async def test_empty_before_any_prediction(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, _ = await _login(client, "dash-empty@example.com")
            response = await client.get("/api/v1/dashboard/summary", headers=_auth(token))

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == {"prediction_available": False, "risks": [], "latest_health_record": None}

    async def test_latest_risk_with_delta_in_percentage_points(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, user = await _login(client, "dash-delta@example.com")
            first = await _record(user, days_ago=10)
            second = await _record(user, days_ago=1)
            await _prediction(user, first, dm="0.2900", htn="0.3000")
            await _prediction(user, second, dm="0.3125", htn="0.2500")
            # 진행 중인 예측은 보지 않는다
            await _prediction(user, second, dm="0.9000", htn="0.9000", status_=PredictionStatus.PENDING)
            response = await client.get("/api/v1/dashboard/summary", headers=_auth(token))

        data = response.json()["data"]
        assert data["prediction_available"] is True
        risks = {risk["disease"]: risk for risk in data["risks"]}
        assert risks["diabetes"]["probability"] == 0.3125
        assert risks["diabetes"]["delta"] == 2.25
        assert risks["hypertension"]["delta"] == -5.0
        # 등급 경계값이 정해지기 전까지 키는 두고 값은 null
        assert "grade" in risks["diabetes"]
        assert risks["diabetes"]["grade"] is None
        assert risks["diabetes"]["predicted_at"].endswith("+09:00")
        assert data["latest_health_record"]["health_record_id"] == second.id

    async def test_delta_is_null_without_previous_prediction(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, user = await _login(client, "dash-first@example.com")
            await _prediction(user, await _record(user, days_ago=1), dm="0.3000", htn="0.2000")
            response = await client.get("/api/v1/dashboard/summary", headers=_auth(token))

        assert all(risk["delta"] is None for risk in response.json()["data"]["risks"])

    async def test_diagnosed_disease_is_not_exposed(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, user = await _login(client, "dash-diag@example.com")
            await User.filter(id=user.id).update(dm_diagnosed=True)
            await _prediction(user, await _record(user, days_ago=1), dm=None, htn="0.2000")
            response = await client.get("/api/v1/dashboard/summary", headers=_auth(token))

        assert [risk["disease"] for risk in response.json()["data"]["risks"]] == ["hypertension"]

    async def test_both_diagnosed_hides_risks(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, user = await _login(client, "dash-both@example.com")
            await User.filter(id=user.id).update(dm_diagnosed=True, htn_diagnosed=True)
            record = await _record(user, days_ago=1)
            await _prediction(user, record, dm="0.3000", htn="0.2000")
            response = await client.get("/api/v1/dashboard/summary", headers=_auth(token))

        data = response.json()["data"]
        assert data["prediction_available"] is False
        assert data["risks"] == []
        assert data["latest_health_record"]["health_record_id"] == record.id


class TestDashboardTrendsAPI(TestCase):
    async def test_points_join_measurements_and_risks_by_record(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, user = await _login(client, "dash-trend@example.com")
            await User.filter(id=user.id).update(htn_diagnosed=True)
            older = await _record(user, days_ago=20, weight_kg=Decimal("65.0"), sbp=130)
            newer = await _record(user, days_ago=2, weight_kg=Decimal("64.2"), hba1c=Decimal("5.8"))
            await _prediction(user, older, dm="0.3000", htn="0.4000")
            response = await client.get("/api/v1/dashboard/trends", headers=_auth(token))

        assert response.status_code == status.HTTP_200_OK
        points = response.json()["data"]["points"]
        assert [point["health_record_id"] for point in points] == [older.id, newer.id]
        assert points[0]["measurements"] == {
            "weight_kg": 65.0,
            "waist_cm": None,
            "sbp": 130,
            "dbp": None,
            "fasting_glucose": None,
            "hba1c": None,
        }
        # 고혈압 진단자라 당뇨만 남는다
        assert [(risk["disease"], risk["probability"]) for risk in points[0]["risks"]] == [("diabetes", 0.3)]
        assert points[1]["risks"] == []
        assert points[0]["recorded_at"].endswith("+09:00")

    async def test_same_period_rule_as_health_records(self):
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, _ = await _login(client, "dash-period@example.com")
            response = await client.get(
                "/api/v1/dashboard/trends",
                params={"start_date": (today - timedelta(days=800)).isoformat()},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
