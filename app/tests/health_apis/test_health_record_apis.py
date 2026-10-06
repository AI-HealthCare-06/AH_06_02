from datetime import datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.health_records import HealthRecord
from app.models.users import User
from app.tests.auth_apis.test_signup_api import signup_body

PASSWORD = "dango1234"
URL = "/api/v1/health-records"


async def _login(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email))
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestCreateHealthRecordAPI(TestCase):
    async def test_simple_record_is_saved_with_server_bmi(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-simple@example.com")
            response = await client.post(
                URL,
                json={"input_mode": "simple", "weight_kg": 64.0, "waist_cm": 78.5, "walking_days": 3},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["input_mode"] == "simple"
        # 키 164cm (가입 프로필) · 64kg -> 23.795 -> 23.8
        assert data["bmi"] == 23.8
        # DATETIME 은 KST naive 로 저장하고 응답에는 +09:00 을 붙인다
        assert data["recorded_at"].endswith("+09:00")
        record = await HealthRecord.get(id=data["health_record_id"])
        assert record.walking_days == 3
        assert record.bmi == Decimal("23.8")

    async def test_records_accumulate_instead_of_overwriting(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-accumulate@example.com")
            await client.post(URL, json={"input_mode": "simple", "weight_kg": 64.0}, headers=_auth(token))
            await client.post(URL, json={"input_mode": "simple", "weight_kg": 63.0}, headers=_auth(token))

        user = await User.get(email="hr-accumulate@example.com")
        assert await HealthRecord.filter(user_id=user.id).count() == 2

    async def test_profile_is_required_for_simple_and_detail(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-profile@example.com")
            await User.filter(email="hr-profile@example.com").update(height_cm=None)
            response = await client.post(URL, json={"input_mode": "detail", "sbp": 120}, headers=_auth(token))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "HLTH_PROFILE_INCOMPLETE"

    async def test_daily_record_needs_one_value_but_no_profile(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-daily@example.com")
            await User.filter(email="hr-daily@example.com").update(height_cm=None)
            empty = await client.post(URL, json={"input_mode": "daily"}, headers=_auth(token))
            saved = await client.post(URL, json={"input_mode": "daily", "sbp": 118}, headers=_auth(token))

        assert empty.status_code == status.HTTP_400_BAD_REQUEST
        assert empty.json()["error"]["code"] == "VALIDATION_ERROR"
        assert saved.status_code == status.HTTP_201_CREATED
        assert saved.json()["data"]["bmi"] is None

    async def test_out_of_range_is_rejected_with_allowed_range(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-range@example.com")
            response = await client.post(
                URL,
                json={"input_mode": "detail", "weight_kg": 25.0, "fasting_glucose": 600, "sitting_minutes": 1441},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error = response.json()["error"]
        assert error["code"] == "HLTH_VALUE_OUT_OF_RANGE"
        assert {"field": "weight_kg", "min": 30, "max": 200} in error["fields"]
        assert {"field": "fasting_glucose", "min": 40, "max": 500} in error["fields"]
        assert {"field": "sitting_minutes", "min": 0, "max": 1440} in error["fields"]
        user = await User.get(email="hr-range@example.com")
        assert not await HealthRecord.filter(user_id=user.id).exists()

    async def test_alcohol_amount_zero_only_for_non_drinker(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-alcohol@example.com")
            drinker = await client.post(
                URL,
                json={"input_mode": "simple", "alcohol_frequency": 3, "alcohol_amount": 0},
                headers=_auth(token),
            )
            non_drinker = await client.post(
                URL,
                json={"input_mode": "simple", "alcohol_frequency": 1, "alcohol_amount": 0},
                headers=_auth(token),
            )

        assert drinker.json()["error"]["code"] == "HLTH_VALUE_OUT_OF_RANGE"
        assert drinker.json()["error"]["fields"][0]["field"] == "alcohol_amount"
        assert non_drinker.status_code == status.HTTP_201_CREATED

    async def test_strength_days_is_not_capped_at_five(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-strength@example.com")
            response = await client.post(URL, json={"input_mode": "simple", "strength_days": 7}, headers=_auth(token))

        # min(value, 5) 는 학습 전처리다. API 는 0~7 을 그대로 받는다
        assert response.status_code == status.HTTP_201_CREATED
        assert (await HealthRecord.get(id=response.json()["data"]["health_record_id"])).strength_days == 7

    async def test_fields_outside_the_mode_are_rejected(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-mode@example.com")
            simple_with_bp = await client.post(URL, json={"input_mode": "simple", "sbp": 120}, headers=_auth(token))
            detail_with_tc = await client.post(
                URL, json={"input_mode": "detail", "total_cholesterol": 180}, headers=_auth(token)
            )
            daily_with_smoking = await client.post(
                URL, json={"input_mode": "daily", "weight_kg": 64.0, "smoking_current": True}, headers=_auth(token)
            )

        for response in (simple_with_bp, detail_with_tc, daily_with_smoking):
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_unbounded_fields_only_check_db_type(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-dbtype@example.com")
            too_wide = await client.post(URL, json={"input_mode": "detail", "hba1c": 100.0}, headers=_auth(token))
            fits = await client.post(URL, json={"input_mode": "detail", "hba1c": 99.9}, headers=_auth(token))

        # HbA1c 는 명세에 범위가 없어 DECIMAL(3,1) 한계만 본다
        assert too_wide.json()["error"]["code"] == "VALIDATION_ERROR"
        assert fits.status_code == status.HTTP_201_CREATED


class TestListHealthRecordsAPI(TestCase):
    async def test_lists_own_records_newest_first(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-list@example.com")
            other = await _login(client, "hr-list-other@example.com")
            await client.post(URL, json={"input_mode": "simple", "weight_kg": 64.0}, headers=_auth(token))
            await client.post(URL, json={"input_mode": "daily", "weight_kg": 63.5}, headers=_auth(token))
            await client.post(URL, json={"input_mode": "simple", "weight_kg": 80.0}, headers=_auth(other))
            response = await client.get(URL, headers=_auth(token))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["size"] == 20
        assert [item["weight_kg"] for item in data["items"]] == [63.5, 64.0]
        assert "total_cholesterol" not in data["items"][0]

    async def test_default_period_excludes_records_older_than_12_months(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-old@example.com")
            user = await User.get(email="hr-old@example.com")
            old = datetime.now(config.TIMEZONE) - relativedelta(months=13)
            await HealthRecord.create(user_id=user.id, recorded_at=old, weight_kg=Decimal("70.0"))
            response = await client.get(URL, headers=_auth(token))

        assert response.json()["data"]["total"] == 0

    async def test_start_date_before_12_months_is_rejected_not_clipped(self):
        today = datetime.now(config.TIMEZONE).date()
        earliest = today - relativedelta(months=12)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-period@example.com")
            response = await client.get(
                URL, params={"start_date": (earliest - timedelta(days=1)).isoformat()}, headers=_auth(token)
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["fields"] == [{"field": "start_date", "min": earliest.isoformat(), "max": today.isoformat()}]

    async def test_reversed_period_is_rejected(self):
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-reversed@example.com")
            response = await client.get(
                URL,
                params={"start_date": today.isoformat(), "end_date": (today - timedelta(days=1)).isoformat()},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_end_date_includes_the_whole_kst_day(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-kst@example.com")
            user = await User.get(email="hr-kst@example.com")
            today = datetime.now(config.TIMEZONE).date()
            late = datetime.combine(today, datetime.max.time(), tzinfo=config.TIMEZONE).replace(microsecond=0)
            await HealthRecord.create(user_id=user.id, recorded_at=late)
            response = await client.get(URL, params={"end_date": today.isoformat()}, headers=_auth(token))

        assert response.json()["data"]["total"] == 1
        assert response.json()["data"]["items"][0]["recorded_at"] == f"{today.isoformat()}T23:59:59+09:00"

    async def test_page_size_is_capped_at_100(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "hr-size@example.com")
            response = await client.get(URL, params={"size": 101}, headers=_auth(token))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
