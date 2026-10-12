"""D 화면은 오늘 예정 기회와 서버에 저장된 값을 사용한다."""

from datetime import datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.apis.v1.challenge_routers import get_recommendation_service
from app.core import config
from app.main import app
from app.models.challenges import (
    Challenge,
    ChallengeCategory,
    ContextType,
    GoalType,
    OccurrenceStatus,
    Reward,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
    UserReward,
    VerificationType,
)
from app.models.health_records import HealthRecord
from app.models.users import User
from app.services.recommendations import RecommendationService
from app.tests.challenge_apis.test_challenge_core_apis import _auth, _login
from app.tests.challenge_apis.test_d_apis import _login as login_user
from app.tests.d_fixtures import fake_artifact, make_card, make_cycle, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges


class TestDScreenData(TestCase):
    async def test_active_mission_returns_only_own_today_occurrences_with_snapshot_goal(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "screen-occurrences@example.com")
            cycle = await make_cycle(user_id, start=today)
            challenge = await Challenge.create(
                code="SCREEN-TIMER",
                title="식후 걷기",
                category=ChallengeCategory.ACTIVITY,
                goal_type=GoalType.DURATION,
                verification_type=VerificationType.TIMER,
                context_type=ContextType.MEAL,
                context_slots=["lunch", "dinner"],
                target_value=30,
                unit="분",
                manual_fallback_allowed=False,
            )
            mission = await UserChallenge.create(
                user_id=user_id,
                challenge_id=challenge.id,
                cycle_id=cycle.id,
                start_date=today,
                end_date=today + timedelta(days=27),
                daily_target_count_snapshot=2,
                target_value_snapshot=Decimal("10"),
                duration_days_snapshot=28,
                goal_config_snapshot={"unit": "분", "daily_xp": 36},
            )
            lunch = await UserChallengeOccurrence.create(
                user_challenge_id=mission.id,
                scheduled_date=today,
                slot_code="lunch",
                status=OccurrenceStatus.COMPLETED,
            )
            dinner = await UserChallengeOccurrence.create(
                user_challenge_id=mission.id,
                scheduled_date=today,
                slot_code="dinner",
            )
            await UserChallengeOccurrence.create(
                user_challenge_id=mission.id,
                scheduled_date=today + timedelta(days=1),
                slot_code="lunch",
            )
            other = await User.create(email="screen-other@example.com", nickname="다른 사용자", password_hash="x")
            await UserChallenge.create(
                user_id=other.id,
                challenge_id=challenge.id,
                start_date=today,
                end_date=today,
                daily_target_count_snapshot=1,
                duration_days_snapshot=1,
            )
            response = await client.get("/api/v1/user-challenges?status=active", headers=_auth(token))

        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["target_value"] == 10
        assert item["unit"] == "분"
        assert item["today_date"] == today.isoformat()
        assert item["manual_fallback_allowed"] is False
        assert item["status"] == str(UserChallengeStatus.ACTIVE)
        assert item["today_occurrences"] == [
            {"occurrence_id": lunch.id, "slot_code": "lunch", "sequence_no": 1, "status": "completed"},
            {"occurrence_id": dinner.id, "slot_code": "dinner", "sequence_no": 1, "status": "planned"},
        ]

    async def test_rewards_are_paginated_and_never_include_another_users_items(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "screen-rewards@example.com")
            other = await User.create(email="reward-other@example.com", nickname="다른 사용자", password_hash="x")
            first = await Reward.create(
                code="screen-one", name="첫 보상", motivation_type="grow", reward_kind="item", unlock_condition="테스트"
            )
            second = await Reward.create(
                code="screen-two",
                name="다른 보상",
                motivation_type="collect",
                reward_kind="badge",
                unlock_condition="테스트",
            )
            await UserReward.create(
                user_id=user_id, reward_id=first.id, item_level=2, acquired_at=datetime.now(config.TIMEZONE)
            )
            await UserReward.create(user_id=other.id, reward_id=second.id, acquired_at=datetime.now(config.TIMEZONE))
            response = await client.get("/api/v1/rewards/me?page=1&size=1", headers=_auth(token))
            unauthorized = await client.get("/api/v1/rewards/me")
            invalid = await client.get("/api/v1/rewards/me?size=101", headers=_auth(token))
            empty = await client.get("/api/v1/rewards/me?page=2&size=1", headers=_auth(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["reward_id"] == first.id
        assert data["items"][0]["item_level"] == 2
        assert data["items"][0]["acquired_at"].endswith("+09:00")
        assert empty.json()["data"]["items"] == []
        assert unauthorized.status_code == 401
        assert invalid.status_code == 400

    async def test_generated_recommendation_exposes_server_capacity_and_goal(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        await Challenge.filter(code="CH_NO_SMOKE_TODAY").update(reward_xp=21)
        artifact = fake_artifact({"diabetes": {"smoking_current": 40}})
        app.dependency_overrides[get_recommendation_service] = lambda: RecommendationService(lambda: artifact)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await login_user(
                    client, "screen-reco@example.com", dm_diagnosed=True, htn_diagnosed=True
                )
                await make_target(user.id, ["smoking_current"])
                await HealthRecord.create(
                    user_id=user.id, recorded_at=datetime.now(config.TIMEZONE), smoking_current=True
                )
                response = await client.post("/api/v1/challenge-recommendations/generate", headers=headers)
        finally:
            app.dependency_overrides.pop(get_recommendation_service, None)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["remaining_slots"] == 2
        card = data["items"][0]
        assert card["daily_target_count"] == 1
        assert card["verification_type"] == "manual"
        assert card["daily_xp"] == 21
        assert card["safety_check_required"] is False

    async def test_d_frontend_and_shared_client_are_served_without_exposing_repository_files(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            html = await client.get("/frontend/d/")
            module = await client.get("/frontend/shared/api.mjs")
            outside = await client.get("/frontend/%2e%2e/app/core/config.py")
        assert html.status_code == 200
        assert "data-dango-screens" in html.text
        assert module.status_code == 200
        assert "createApiClient" in module.text
        assert outside.status_code == 404

    async def test_excluded_recommendations_report_whether_user_can_restore_them(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "screen-suppressed@example.com")
            cycle = await make_cycle(user_id, ["smoking_current"])
            challenge = await Challenge.get(code="CH_NO_SMOKE_TODAY")
            card = await make_card(user_id, challenge, cycle)
            await client.patch(
                f"/api/v1/challenge-recommendations/{card.id}", json={"action": "not_applicable"}, headers=_auth(token)
            )
            excluded = await client.get("/api/v1/challenge-recommendations", headers=_auth(token))
            await client.patch(f"/api/v1/challenge-recommendations/{card.id}/unsuppress", headers=_auth(token))
            restored = await client.get("/api/v1/challenge-recommendations", headers=_auth(token))
        assert excluded.json()["data"]["items"][0]["suppressed_until_manual"] is True
        assert restored.json()["data"]["items"][0]["suppressed_until_manual"] is False
