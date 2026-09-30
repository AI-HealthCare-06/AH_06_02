from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import User
from app.repositories.user_repository import LOGIN_FAIL_LIMIT
from app.tests.auth_apis.test_signup_api import signup_body

PASSWORD = "dango1234"


class TestLoginAPI(TestCase):
    async def test_login_success(self):
        email = "login@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_body(email=email))
            response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        # AUTH-03 응답 계약 — 토큰 둘과 요약 프로필
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["user"]["nickname"] == "수빈"
        assert data["user"]["level"] == 1
        assert data["user"]["total_xp"] == 0
        assert any("refresh_token" in header for header in response.headers.get_list("set-cookie"))

    async def test_login_invalid_credentials(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpass123"},
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

    async def test_login_locks_account_after_repeated_failures(self):
        """5회 연속 실패하면 10분 잠근다 (REQ-USER-004)."""
        email = "lockme@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_body(email=email))

            for _ in range(LOGIN_FAIL_LIMIT - 1):
                res = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrongpass123"})
                assert res.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"

            locking = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrongpass123"})
            # 잠긴 뒤에는 올바른 비밀번호로도 막힌다
            after_lock = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

        assert locking.json()["error"]["code"] == "AUTH_ACCOUNT_LOCKED"
        assert after_lock.status_code == status.HTTP_403_FORBIDDEN
        assert after_lock.json()["error"]["code"] == "AUTH_ACCOUNT_LOCKED"

        user = await User.get(email=email)
        assert user.login_fail_count >= LOGIN_FAIL_LIMIT
        assert user.locked_until is not None

    async def test_login_success_resets_fail_count(self):
        email = "reset@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_body(email=email))
            await client.post("/api/v1/auth/login", json={"email": email, "password": "wrongpass123"})
            await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

        user = await User.get(email=email)
        assert user.login_fail_count == 0
        assert user.locked_until is None
