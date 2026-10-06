from datetime import date

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.challenges import (
    Challenge,
    ChallengeCategory,
    ChallengeRecommendation,
    GoalType,
    RecommendationSourceType,
    UserChallenge,
    UserChallengeStatus,
)
from app.models.users import User
from app.tests.auth_apis.test_signup_api import signup_body
from app.tests.d_fixtures import make_cycle

PASSWORD = "dango1234"


async def _login(client: AsyncClient, email: str) -> tuple[int, str]:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email))
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    token = str(login.json()["data"]["access_token"])
    user = await User.get(email=email)
    return user.id, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _challenge(code: str, *, safety: bool = False) -> Challenge:
    return await Challenge.create(
        code=code,
        title=code,
        category=ChallengeCategory.ACTIVITY,
        factor_key="physical_activity_low",
        goal_type=GoalType.BOOLEAN,
        safety_check_required=safety,
    )


async def _recommendation(*, user_id: int, challenge_id: int, rank: int = 1) -> ChallengeRecommendation:
    cycle = await make_cycle(user_id, ["physical_activity_low"])
    return await ChallengeRecommendation.create(
        user_id=user_id,
        challenge_id=challenge_id,
        cycle_id=cycle.id,
        source_type=RecommendationSourceType.PREDICTION_PERSONAL,
        factor_key="physical_activity_low",
        rank=rank,
        recommended_at="2026-10-01T09:00:00+09:00",
    )


class TestChallengeStartAPI(TestCase):
    async def test_start_challenge_success(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "d-start@example.com")
            challenge = await _challenge("TEST-ROUTER-START")
            recommendation = await _recommendation(user_id=user_id, challenge_id=challenge.id)
            response = await client.post(
                "/api/v1/user-challenges",
                json={
                    "recommendation_ids": [recommendation.id],
                    "safety_confirmed": False,
                },
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["active_count"] == 1
        assert data["items"][0]["challenge_id"] == challenge.id
        assert data["items"][0]["status"] == "active"

    async def test_start_requires_safety_confirmation(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "d-safe@example.com")
            challenge = await _challenge("TEST-ROUTER-SAFE", safety=True)
            recommendation = await _recommendation(user_id=user_id, challenge_id=challenge.id)
            response = await client.post(
                "/api/v1/user-challenges",
                json={"recommendation_ids": [recommendation.id]},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "CHLG_SAFETY_CONFIRMATION_REQUIRED"


class TestChallengeStopAPI(TestCase):
    async def test_stop_challenge_success(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "d-stop@example.com")
            challenge = await _challenge("TEST-ROUTER-STOP")
            item = await UserChallenge.create(
                user_id=user_id,
                challenge_id=challenge.id,
                status=UserChallengeStatus.ACTIVE,
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 7),
                daily_target_count_snapshot=1,
                target_value_snapshot=None,
                duration_days_snapshot=7,
            )
            response = await client.post(
                f"/api/v1/user-challenges/{item.id}/stop",
                json={"stop_reason": "테스트 중단"},
                headers=_auth(token),
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "abandoned"
        assert data["stop_reason"] == "테스트 중단"
        assert data["stopped_at"] is not None
