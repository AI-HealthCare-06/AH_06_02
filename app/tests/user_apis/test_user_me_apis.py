from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.tests.auth_apis.test_signup_api import signup_body

PASSWORD = "dango1234"


async def _login(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email))
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return str(res.json()["data"]["access_token"])


class TestUserMeApis(TestCase):
    async def test_get_user_me_success(self):
        email = "me@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, email)
            response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["email"] == email
        assert data["nickname"] == "수빈"
        assert data["level"] == 1
        assert data["total_xp"] == 0
        # 비밀번호 해시는 어떤 경우에도 응답에 실리지 않는다
        assert "password_hash" not in data

    async def test_update_user_me_success(self):
        email = "update_me@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, email)
            response = await client.patch(
                "/api/v1/users/me",
                json={"nickname": "수정후", "motivation_type": "grow"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["nickname"] == "수정후"
        assert data["motivation_type"] == "grow"

    async def test_get_user_me_unauthorized(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/users/me")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
