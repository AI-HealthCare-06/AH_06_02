from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.apis.v1.challenge_routers import get_recommendation_service
from app.core import config
from app.main import app
from app.models.challenges import Challenge, UserMonster
from app.models.health_records import HealthRecord
from app.models.users import User
from app.services.attack_cycles import today_kst
from app.services.recommendations import RecommendationService
from app.tests.auth_apis.test_signup_api import signup_body
from app.tests.d_fixtures import fake_artifact, make_card, make_cycle, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

PASSWORD = "dango1234"


async def _login(client: AsyncClient, email: str, **overrides: object) -> tuple[User, dict[str, str]]:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email, **overrides))
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return await User.get(email=email), {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def _seed() -> dict[str, Challenge]:
    await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
    return {item.code: item for item in await Challenge.all()}


class TestDChallengeAPIs(TestCase):
    async def test_generate_returns_cards_with_target_and_model_version(self) -> None:
        await _seed()
        artifact = fake_artifact({"diabetes": {"smoking_current": 40.0}, "hypertension": {"smoking_current": 30.0}})
        app.dependency_overrides[get_recommendation_service] = lambda: RecommendationService(lambda: artifact)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                user, headers = await _login(client, "api-gen@example.com", dm_diagnosed=True, htn_diagnosed=True)
                await make_target(user.id, ["smoking_current"])
                await HealthRecord.create(
                    user_id=user.id, recorded_at=datetime.now(config.TIMEZONE), smoking_current=True
                )
                generated = await client.post("/api/v1/challenge-recommendations/generate", headers=headers)
                listed = await client.get("/api/v1/challenge-recommendations", headers=headers)
        finally:
            app.dependency_overrides.pop(get_recommendation_service, None)

        assert generated.status_code == status.HTTP_200_OK
        data = generated.json()["data"]
        assert data["total"] == 1
        assert data["model_version"] == "test-model"
        card = data["items"][0]
        assert card["factor_score"] == 40.0
        assert card["target_monster"]["code"].startswith("t-")
        assert listed.json()["data"]["items"][0]["recommendation_id"] == card["recommendation_id"]

    async def test_generate_without_artifact_is_unavailable(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, headers = await _login(client, "api-noart@example.com")
            response = await client.post("/api/v1/challenge-recommendations/generate", headers=headers)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["error"]["code"] == "CHLG_RECOMMENDATION_UNAVAILABLE"

    async def test_invalid_cooldown_string(self) -> None:
        challenges = await _seed()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers = await _login(client, "api-cool@example.com")
            cycle = await make_cycle(user.id, ["smoking_current"])
            card = await make_card(user.id, challenges["CH_NO_SMOKE_TODAY"], cycle)
            response = await client.patch(
                f"/api/v1/challenge-recommendations/{card.id}",
                json={"action": "rejected", "cooldown_choice": "14d"},
                headers=headers,
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "CHLG_INVALID_COOLDOWN"

    async def test_start_log_and_read_back(self) -> None:
        challenges = await _seed()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers = await _login(client, "api-flow@example.com")
            cycle = await make_cycle(user.id, ["smoking_current"])
            card = await make_card(user.id, challenges["CH_NO_SMOKE_TODAY"], cycle)
            started = await client.post(
                "/api/v1/user-challenges", json={"recommendation_ids": [card.id]}, headers=headers
            )
            mission_id = started.json()["data"]["items"][0]["user_challenge_id"]
            occurred = today_kst().isoformat() + "T00:00:01+09:00"
            logged = await client.post(
                f"/api/v1/user-challenges/{mission_id}/logs",
                json={"occurred_at": occurred, "verification_method": "manual"},
                headers=headers,
            )
            missions = await client.get("/api/v1/user-challenges", headers=headers)
            logs = await client.get(f"/api/v1/user-challenges/{mission_id}/logs", headers=headers)
            monsters = await client.get("/api/v1/monsters/me", headers=headers)

        assert started.status_code == status.HTTP_201_CREATED
        assert started.json()["data"]["items"][0]["cycle_id"] == cycle.id
        assert logged.status_code == status.HTTP_201_CREATED
        body = logged.json()["data"]
        assert body["xp_granted"] == 36
        assert body["weekly_progress"] == 10
        assert body["reward"] is None

        item = missions.json()["data"]["items"][0]
        assert item["cycle_week"] == 1
        assert item["completed_count"] == 1
        assert item["scheduled_opportunity_count"] == 28
        assert item["progress_rate"] == round(1 / 28, 4)
        assert item["habit_established"] is None
        assert item["target_monster"]["monster_id"]

        log = logs.json()["data"]["items"][0]
        assert log["occurred_at"].endswith("+09:00")

        [monster] = monsters.json()["data"]["items"]
        assert monster["is_target"] is True
        assert monster["weekly_progress"] == 10
        assert monster["impact_score"] == 80
        assert monster["seal_progress"] is None

    async def test_monster_book_is_empty_without_master(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, headers = await _login(client, "api-book@example.com")
            response = await client.get("/api/v1/monsters/me", headers=headers)

        # monsters 마스터 값이 없으면 빈 목록이다
        assert response.json()["data"] == {"items": []}

    async def test_last_week_progress_reads_as_zero(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers = await _login(client, "api-week@example.com")
            target = await make_target(user.id, ["smoking_current"])
            await UserMonster.filter(id=target.id).update(
                weekly_progress=40, progress_week_start=today_kst() - timedelta(days=14)
            )
            response = await client.get("/api/v1/monsters/me", headers=headers)

        assert response.json()["data"]["items"][0]["weekly_progress"] == 0
