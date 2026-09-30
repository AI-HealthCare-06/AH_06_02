from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import MotivationType, User, UserStatus

BASE_SIGNUP = {
    "email": "signup@example.com",
    "password": "dango1234",
    "nickname": "수빈",
    "birth_year": 1998,
    "sex": "F",
    "height_cm": 164.0,
    "motivation_type": "collect",
    "dm_diagnosed": False,
    "htn_diagnosed": False,
    "dm_medication": False,
    "htn_medication": False,
    "disclaimer_agreed": True,
}


def signup_body(**overrides: object) -> dict[str, object]:
    return {**BASE_SIGNUP, **overrides}


class TestSignupAPI(TestCase):
    async def test_signup_success(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_body())

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["success"] is True
        assert body["data"]["access_token"]
        assert body["data"]["refresh_token"]

        user = await User.get(email=BASE_SIGNUP["email"])
        assert user.nickname == "수빈"
        assert user.level == 1
        assert user.total_xp == 0
        assert user.status is UserStatus.ACTIVE
        assert user.motivation_type is MotivationType.COLLECT
        assert user.disclaimer_agreed_at is not None
        # 평문 비밀번호가 그대로 저장되면 안 된다 (NFR-SEC-003)
        assert user.password_hash != BASE_SIGNUP["password"]

    async def test_signup_invalid_email(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_body(email="invalid-email"))

        # 공통 규칙상 요청 값 검증 실패는 VALIDATION_ERROR(400)로 내린다
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_signup_weak_password(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_body(password="short"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_signup_duplicated_email(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_body(email="dup@example.com"))
            response = await client.post("/api/v1/auth/signup", json=signup_body(email="dup@example.com"))

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["error"]["code"] == "AUTH_EMAIL_DUPLICATED"

    async def test_signup_requires_disclaimer(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/signup",
                json=signup_body(email="nodisclaimer@example.com", disclaimer_agreed=False),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_signup_rejects_under_age(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/signup",
                json=signup_body(email="child@example.com", birth_year=2020),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_check_email_available(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/check-email", params={"email": "nobody@example.com"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["available"] is True
