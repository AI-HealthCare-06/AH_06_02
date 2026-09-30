import re

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.tests.auth_apis.test_signup_api import signup_body

PASSWORD = "dango1234"


class TestJWTTokenRefreshAPI(TestCase):
    async def test_token_refresh_with_body(self):
        """AUTH-04 — 명세대로 본문에 refresh_token을 실어 보낸다."""
        email = "refresh@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_body(email=email))
            login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            refresh_token = login.json()["data"]["refresh_token"]

            client.cookies.clear()
            response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["access_token"]

    async def test_token_refresh_falls_back_to_cookie(self):
        email = "refresh_cookie@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_body(email=email))
            login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

            match = re.search(r"refresh_token=([^;]+)", login.headers.get("set-cookie", ""))
            client.cookies["refresh_token"] = match.group(1) if match else ""

            response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["access_token"]

    async def test_token_refresh_missing_token(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "AUTH_TOKEN_INVALID"

    async def test_token_refresh_rejects_garbage(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-token"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "AUTH_TOKEN_INVALID"
