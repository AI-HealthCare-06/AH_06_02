import re

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.tests.auth_apis.test_signup_api import signup_body

PASSWORD = "dango1234"


class TestJWTTokenRefreshAPI(TestCase):
    async def test_token_refresh_success(self):
        email = "refresh@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_body(email=email))
            login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

            set_cookie = login_response.headers.get("set-cookie", "")
            match = re.search(r"refresh_token=([^;]+)", set_cookie)
            client.cookies["refresh_token"] = match.group(1) if match else ""

            response = await client.get("/api/v1/auth/token/refresh")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["access_token"]

    async def test_token_refresh_missing_token(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/token/refresh")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "AUTH_TOKEN_INVALID"
