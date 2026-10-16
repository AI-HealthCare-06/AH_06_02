"""후보 소진과 자료 부재를 HTTP 응답에서 구분한다."""

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.apis.v1.challenge_routers import get_recommendation_service
from app.dependencies.security import get_request_user
from app.main import app
from app.models.challenges import Challenge, UserChallenge, UserChallengeStatus
from app.models.users import User
from app.services.recommendations import RecommendationService
from app.tests.d_fixtures import fake_artifact, make_cycle


class TestRecommendationUnavailable(TestCase):
    async def test_active_only_candidate_returns_no_additional_candidates(self):
        user = await User.create(
            email="empty@example.com", password_hash="x", nickname="테스트", dm_diagnosed=True, htn_diagnosed=True
        )
        cycle = await make_cycle(user.id, ["smoking_current"])
        challenge = await Challenge.create(
            code="CH_NO_SMOKE_TODAY",
            title="오늘 안 피우기",
            category="smoking",
            factor_key="smoking_current",
            goal_type="boolean",
            verification_type="manual",
        )
        await UserChallenge.create(
            user_id=user.id,
            challenge_id=challenge.id,
            cycle_id=cycle.id,
            status=UserChallengeStatus.ACTIVE,
            start_date="2026-10-15",
            end_date="2026-11-11",
            duration_days_snapshot=28,
            daily_target_count_snapshot=1,
        )
        service = RecommendationService(lambda: fake_artifact())
        app.dependency_overrides[get_request_user] = lambda: user
        app.dependency_overrides[get_recommendation_service] = lambda: service
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/challenge-recommendations/generate")
            assert response.status_code == 409
            assert response.json()["error"]["reason"] == "no_additional_candidates"
        finally:
            app.dependency_overrides.clear()
