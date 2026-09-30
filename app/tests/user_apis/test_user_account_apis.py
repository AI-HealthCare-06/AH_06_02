from datetime import timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import User, UserStatus
from app.repositories.user_repository import PURGE_AFTER_DAYS
from app.tests.auth_apis.test_signup_api import signup_body

PASSWORD = "dango1234"


async def _login(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email))
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestDiagnosisAPI(TestCase):
    async def test_update_diagnosis(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "diag@example.com")
            response = await client.patch(
                "/api/v1/users/me/diagnosis",
                json={
                    "dm_diagnosed": True,
                    "htn_diagnosed": False,
                    "dm_medication": True,
                    "htn_medication": False,
                },
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["dm_diagnosed"] is True
        assert data["dm_medication"] is True
        # 기획서 v19 2.3 — 한 질환만 진단이면 나머지 예측은 그대로 제공한다
        assert data["prediction_enabled"] is True

    async def test_prediction_disabled_only_when_both_diagnosed(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "both@example.com")
            response = await client.patch(
                "/api/v1/users/me/diagnosis",
                json={
                    "dm_diagnosed": True,
                    "htn_diagnosed": True,
                    "dm_medication": False,
                    "htn_medication": False,
                },
                headers=_auth(token),
            )

        assert response.json()["data"]["prediction_enabled"] is False


class TestPasswordChangeAPI(TestCase):
    async def test_change_password_success(self):
        email = "pw@example.com"
        new_password = "dango5678"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, email)
            response = await client.patch(
                "/api/v1/users/me/password",
                json={"current_password": PASSWORD, "new_password": new_password},
                headers=_auth(token),
            )
            relogin = await client.post("/api/v1/auth/login", json={"email": email, "password": new_password})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["password_changed"] is True
        assert relogin.status_code == status.HTTP_200_OK

    async def test_change_password_wrong_current(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "pw_wrong@example.com")
            response = await client.patch(
                "/api/v1/users/me/password",
                json={"current_password": "wrongpass123", "new_password": "dango5678"},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    async def test_change_password_rejects_same_value(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "pw_same@example.com")
            response = await client.patch(
                "/api/v1/users/me/password",
                json={"current_password": PASSWORD, "new_password": PASSWORD},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_change_password_rejects_weak_value(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "pw_weak@example.com")
            response = await client.patch(
                "/api/v1/users/me/password",
                json={"current_password": PASSWORD, "new_password": "short"},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestWithdrawAPI(TestCase):
    async def test_withdraw_success(self):
        email = "bye@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, email)
            response = await client.request(
                "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=_auth(token)
            )
            # 탈퇴 후에는 토큰이 살아 있어도 접근이 막힌다
            after = await client.get("/api/v1/users/me", headers=_auth(token))
            relogin = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["withdrawn_at"]
        assert data["purge_at"]

        user = await User.get(email=email)
        assert user.status is UserStatus.WITHDRAWN
        assert user.withdrawn_at is not None
        # 행은 지우지 않는다 (REQ-USER-009)
        assert user.id is not None

        from datetime import datetime

        purge_at = datetime.fromisoformat(data["purge_at"])
        withdrawn_at = datetime.fromisoformat(data["withdrawn_at"])
        assert purge_at - withdrawn_at == timedelta(days=PURGE_AFTER_DAYS)

        assert after.status_code == status.HTTP_401_UNAUTHORIZED
        assert relogin.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_withdraw_wrong_password(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "bye_wrong@example.com")
            response = await client.request(
                "DELETE", "/api/v1/users/me", json={"password": "wrongpass123"}, headers=_auth(token)
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


class TestLevelAPI(TestCase):
    async def test_level_info_starts_at_one(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "level@example.com")
            response = await client.get("/api/v1/users/me/level", headers=_auth(token))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["level"] == 1
        assert data["total_xp"] == 0
        assert data["current_level_xp"] == 0
        assert data["next_level_xp"] is not None

    async def test_level_reflects_granted_xp(self):
        from app.repositories.user_repository import UserRepository

        email = "xp@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, email)
            user = await User.get(email=email)
            await UserRepository().grant_xp(user.id, 180)

            response = await client.get("/api/v1/users/me/level", headers=_auth(token))

        data = response.json()["data"]
        assert data["total_xp"] == 180
        assert data["level"] == 2
        assert data["current_level_xp"] == 80


class TestLogoutAPI(TestCase):
    async def test_logout_clears_cookie(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "logout@example.com")
            response = await client.post("/api/v1/auth/logout", headers=_auth(token))

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["logged_out"] is True
        assert any("refresh_token" in header for header in response.headers.get_list("set-cookie"))

    async def test_logout_requires_auth(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/logout")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
