import logging
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.challenges import ImpactSource, Monster, MonsterState, UserMonster
from app.models.health_records import HealthRecord
from app.models.users import User
from app.services.model_artifact import EXPERIMENTAL_STATUS, ArtifactLoader
from app.tests.auth_apis.test_signup_api import signup_body
from app.tests.d_fixtures import fake_artifact
from scripts.seed.seed_challenges import DEFAULT_CSV as CHALLENGE_CSV
from scripts.seed.seed_challenges import parse_rows, read_csv, upsert_challenges
from scripts.seed.seed_monsters import DEFAULT_CSV as MONSTER_CSV
from scripts.seed.seed_monsters import seed_monsters

PASSWORD = "dango1234"
URL = "/api/v1/health-records"
HOOK = "app.services.health_records.refresh_impact_from_health_record"


async def _login(client: AsyncClient, email: str, **overrides: object) -> dict[str, str]:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email, **overrides))
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


class TestImpactHook(TestCase):
    async def test_called_with_the_saved_record_for_every_mode(self) -> None:
        with patch(HOOK, new_callable=AsyncMock) as hook:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                headers = await _login(client, "hook-call@example.com")
                simple = await client.post(URL, json={"input_mode": "simple", "weight_kg": 64.0}, headers=headers)
                # daily 는 impacts.py 가 안에서 거른다. 호출하는 쪽은 분기하지 않는다
                daily = await client.post(URL, json={"input_mode": "daily", "sbp": 120}, headers=headers)

        user = await User.get(email="hook-call@example.com")
        assert [call.args for call in hook.await_args_list] == [
            (user.id, simple.json()["data"]["health_record_id"]),
            (user.id, daily.json()["data"]["health_record_id"]),
        ]

    async def test_refresh_failure_keeps_the_record(self) -> None:
        with patch(HOOK, new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                headers = await _login(client, "hook-fail@example.com")
                with self.assertLogs("app.services.health_records", level=logging.ERROR) as logs:
                    response = await client.post(URL, json={"input_mode": "simple", "weight_kg": 64.0}, headers=headers)

        assert response.status_code == 201
        assert await HealthRecord.filter(id=response.json()["data"]["health_record_id"]).exists()
        assert any("위협도 갱신 실패" in line for line in logs.output)

    async def test_diagnosed_smoker_gets_a_global_impact_for_cotinine(self) -> None:
        await upsert_challenges(parse_rows(read_csv(CHALLENGE_CSV)))
        await seed_monsters(read_csv(MONSTER_CSV))
        # 숫자는 테스트용이다. 실제 아티팩트 파일과 무관하게 돌도록 주입한다
        artifact = fake_artifact(
            {"diabetes": {"smoking_current": 40.0}, "hypertension": {"smoking_current": 30.0}},
            status=EXPERIMENTAL_STATUS,
        )
        with patch.object(ArtifactLoader, "load", return_value=artifact):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                headers = await _login(client, "hook-diag@example.com", dm_diagnosed=True, htn_diagnosed=True)
                response = await client.post(
                    URL, json={"input_mode": "simple", "weight_kg": 64.0, "smoking_current": True}, headers=headers
                )

        assert response.status_code == 201
        user = await User.get(email="hook-diag@example.com")
        monsters = {item.id: item.code for item in await Monster.all()}
        rows = {monsters[row.monster_id]: row for row in await UserMonster.filter(user_id=user.id)}
        cotinine = rows["cotinine"]
        assert (cotinine.impact_score, cotinine.state, cotinine.impact_source) == (
            40,
            MonsterState.CAUTION,
            ImpactSource.GLOBAL,
        )
        # 다른 캐릭터는 조건 미정·실측 scorer 없음으로 미평가라 행을 만들지 않는다
        assert set(rows) == {"cotinine"}
