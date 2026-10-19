from datetime import date, datetime
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.challenges import VerificationType
from app.tests.challenge_apis.test_challenge_core_apis import _auth, _challenge, _login, _recommendation
from app.tests.d_fixtures import make_cycle


class TestAdventureAPI(TestCase):
    async def test_cycle_ending_on_first_day_of_month_remains_in_history(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "v5-month-boundary@example.com")
            cycle = await make_cycle(user_id, start=date(2026, 9, 4))
            assert cycle.end_date == date(2026, 10, 1)
            response = await client.get("/api/v1/adventure/progress?month=2026-10", headers=_auth(token))
            assert response.status_code == 200
            assert response.json()["data"]["cycles"][0]["cycle_id"] == cycle.id

    async def test_progress_returns_only_own_requested_month(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, token = await _login(client, "v5-calendar@example.com")
            response = await client.get("/api/v1/adventure/progress?month=2026-10", headers=_auth(token))
            assert response.status_code == 200
            assert response.json()["data"]["days"] == []
            assert response.json()["data"]["missions"] == []
            invalid = await client.get("/api/v1/adventure/progress?month=2026-99", headers=_auth(token))
            assert invalid.status_code == 400

    async def test_timer_cannot_be_completed_before_server_duration(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "v5-timer@example.com")
            headers = _auth(token)
            challenge = await _challenge("V5-TIMER")
            challenge.target_value = Decimal("10")
            await challenge.save()
            card = await _recommendation(user_id=user_id, challenge_id=challenge.id)
            started = await client.post(
                "/api/v1/user-challenges", json={"recommendation_ids": [card.id]}, headers=headers
            )
            mission_id = started.json()["data"]["items"][0]["user_challenge_id"]
            timer = await client.post(f"/api/v1/user-challenges/{mission_id}/timers", json={}, headers=headers)
            assert timer.status_code == 200
            timer_id = timer.json()["data"]["timer_session_id"]
            rejected = await client.post(
                f"/api/v1/user-challenges/{mission_id}/logs",
                json={
                    "occurred_at": datetime.now(config.TIMEZONE).isoformat(),
                    "verification_method": "timer",
                    "value": 999,
                    "timer_session_id": timer_id,
                },
                headers=headers,
            )
            assert rejected.status_code == 422

    async def test_recognized_completion_creates_one_hidden_draw(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "v5-complete@example.com")
            headers = _auth(token)
            challenge = await _challenge("V5-MANUAL")
            challenge.verification_type = VerificationType.MANUAL
            await challenge.save()
            card = await _recommendation(user_id=user_id, challenge_id=challenge.id)
            started = await client.post(
                "/api/v1/user-challenges", json={"recommendation_ids": [card.id]}, headers=headers
            )
            mission_id = started.json()["data"]["items"][0]["user_challenge_id"]
            result = await client.post(
                f"/api/v1/user-challenges/{mission_id}/logs",
                json={"occurred_at": datetime.now(config.TIMEZONE).isoformat(), "verification_method": "manual"},
                headers=headers,
            )
            assert result.status_code == 201
            assert result.json()["data"]["reward_draw_id"] > 0
            draws = (await client.get("/api/v1/reward-draws", headers=headers)).json()["data"]
            assert draws["total"] == 1
            assert draws["items"][0]["results"] is None
            assert "cards" not in draws["items"][0]

    async def test_new_account_has_basic_room_and_locked_rewards(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, token = await _login(client, "v5-room@example.com")
            response = await client.get("/api/v1/rewards/catalog", headers=_auth(token))
            assert response.status_code == 200
            items = {item["code"]: item for item in response.json()["data"]["items"]}
            assert items["room-basic-bed"]["owned"] is True
            assert items["explorer-hat"]["owned"] is False
            assert len(items) == 19

    async def test_unowned_gear_is_rejected_and_state_survives_reload(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            _, token = await _login(client, "v5-ownership@example.com")
            denied = await client.patch(
                "/api/v1/adventurer/me", json={"equipment": {"hat": "explorer-hat"}}, headers=_auth(token)
            )
            assert denied.status_code == 400
            accepted = await client.patch(
                "/api/v1/adventurer/me", json={"room": {"bed": "room-basic-bed"}}, headers=_auth(token)
            )
            assert accepted.status_code == 200
            restored = await client.get("/api/v1/adventurer/me", headers=_auth(token))
            assert restored.json()["data"]["room"]["bed"] == "room-basic-bed"
            assert restored.json()["data"]["equipment"] == {}
