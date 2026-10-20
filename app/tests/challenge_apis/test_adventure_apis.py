from datetime import date, datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.challenges import ChallengeTimerSession, VerificationType
from app.services.challenge_timers import ChallengeTimerService, kst, timer_body
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

    async def _started_timer(self, client: AsyncClient, email: str) -> tuple[str, int, int]:
        user_id, token = await _login(client, email)
        challenge = await _challenge(email.split("@")[0].upper())
        challenge.target_value = Decimal("10")
        await challenge.save()
        card = await _recommendation(user_id=user_id, challenge_id=challenge.id)
        started = await client.post(
            "/api/v1/user-challenges", json={"recommendation_ids": [card.id]}, headers=_auth(token)
        )
        mission_id = started.json()["data"]["items"][0]["user_challenge_id"]
        timer = await client.post(f"/api/v1/user-challenges/{mission_id}/timers", json={}, headers=_auth(token))
        return token, mission_id, timer.json()["data"]["timer_session_id"]

    async def test_paused_timer_does_not_count_paused_time(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, mission_id, timer_id = await self._started_timer(client, "v5-pause@example.com")
            user_id = (await client.get("/api/v1/users/me", headers=_auth(token))).json()["data"]["id"]
        service = ChallengeTimerService()
        session = await ChallengeTimerSession.get(id=timer_id)
        t0 = kst(session.started_at)
        paused = await service.pause(user_id, mission_id, timer_id, t0 + timedelta(seconds=100))
        assert paused["paused"] is True
        # 멈춘 동안에는 경과 시간이 늘지 않는다
        frozen = timer_body(await ChallengeTimerSession.get(id=timer_id), t0 + timedelta(seconds=500))
        assert (frozen["elapsed_seconds"], frozen["ready"]) == (100, False)
        assert (await service.pause(user_id, mission_id, timer_id, t0 + timedelta(seconds=550)))["paused"] is True
        resumed = await service.resume(user_id, mission_id, timer_id, t0 + timedelta(seconds=500))
        assert (resumed["paused"], resumed["elapsed_seconds"]) == (False, 100)
        assert (await ChallengeTimerSession.get(id=timer_id)).paused_seconds == 400
        later = timer_body(await ChallengeTimerSession.get(id=timer_id), t0 + timedelta(seconds=999))
        assert (later["elapsed_seconds"], later["ready"]) == (599, False)
        ready = timer_body(await ChallengeTimerSession.get(id=timer_id), t0 + timedelta(seconds=1000))
        assert ready["ready"] is True
        assert (await service.resume(user_id, mission_id, timer_id, t0 + timedelta(seconds=1001)))["paused"] is False

    async def test_paused_time_is_whole_seconds_so_reload_shows_the_same_time(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, mission_id, timer_id = await self._started_timer(client, "v5-pause-second@example.com")
            user_id = (await client.get("/api/v1/users/me", headers=_auth(token))).json()["data"]["id"]
        service = ChallengeTimerService()
        t0 = kst((await ChallengeTimerSession.get(id=timer_id)).started_at)
        paused = await service.pause(user_id, mission_id, timer_id, t0 + timedelta(seconds=3, milliseconds=700))
        stored = await ChallengeTimerSession.get(id=timer_id)
        # 운영 DB 의 DATETIME 은 초 단위라 소수 초를 반올림한다. 멈춘 시각은 초 단위로 잘라 저장한다
        assert stored.paused_at is not None and stored.paused_at.microsecond == 0
        assert timer_body(stored, t0 + timedelta(seconds=60))["elapsed_seconds"] == paused["elapsed_seconds"] == 3
        # 다시 읽는 시각에 소수 초가 있어도 부동소수점 오차로 1초 줄지 않는다
        for micro in range(0, 1_000_000, 997):
            later = t0 + timedelta(seconds=10, microseconds=micro)
            assert timer_body(stored, later)["elapsed_seconds"] == 3, micro

    async def test_pause_and_resume_endpoints_check_owner_and_expiry(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token, mission_id, timer_id = await self._started_timer(client, "v5-pause-api@example.com")
            base = f"/api/v1/user-challenges/{mission_id}/timers/{timer_id}"
            paused = await client.post(f"{base}/pause", headers=_auth(token))
            assert paused.status_code == 200
            assert paused.json()["data"]["paused"] is True
            looked = await client.get(base, headers=_auth(token))
            assert looked.json()["data"]["paused"] is True
            resumed = await client.post(f"{base}/resume", headers=_auth(token))
            assert resumed.json()["data"]["paused"] is False
            _, stranger = await _login(client, "v5-pause-other@example.com")
            assert (await client.post(f"{base}/pause", headers=_auth(stranger))).status_code == 404
            # 만료된 세션은 멈추거나 이어할 수 없다
            await ChallengeTimerSession.filter(id=timer_id).update(
                expires_at=datetime.now(config.TIMEZONE) - timedelta(seconds=1)
            )
            expired = await client.post(f"{base}/pause", headers=_auth(token))
            assert expired.json()["error"]["code"] == "CHLG_VERIFICATION_FAILED"

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

    async def test_draw_is_claimed_by_choosing_one_of_five_cards(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user_id, token = await _login(client, "v5-one-card@example.com")
            headers = _auth(token)
            challenge = await _challenge("V5-ONE-CARD")
            challenge.verification_type = VerificationType.MANUAL
            await challenge.save()
            card = await _recommendation(user_id=user_id, challenge_id=challenge.id)
            started = await client.post(
                "/api/v1/user-challenges", json={"recommendation_ids": [card.id]}, headers=headers
            )
            mission_id = started.json()["data"]["items"][0]["user_challenge_id"]
            logged = await client.post(
                f"/api/v1/user-challenges/{mission_id}/logs",
                json={"occurred_at": datetime.now(config.TIMEZONE).isoformat(), "verification_method": "manual"},
                headers=headers,
            )
            draw_id = logged.json()["data"]["reward_draw_id"]
            three = await client.post(
                f"/api/v1/reward-draws/{draw_id}/claim", json={"positions": [0, 1, 2]}, headers=headers
            )
            assert three.status_code == 400
            one = await client.post(f"/api/v1/reward-draws/{draw_id}/claim", json={"positions": [3]}, headers=headers)
            assert one.status_code == 200
            assert one.json()["data"]["selected_positions"] == [3]
            assert len(one.json()["data"]["results"]) == 1

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
