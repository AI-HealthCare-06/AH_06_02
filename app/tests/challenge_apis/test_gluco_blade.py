from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.utils.security import hash_password
from app.main import app
from app.models.challenges import Challenge, ChallengeLog, Reward, UserChallenge, UserReward, VerificationMethod
from app.models.users import MotivationType, User
from app.services.challenges import ChallengeCoreService, LogResult
from app.tests.d_fixtures import make_card, make_cycle
from scripts.seed.seed_challenges import DEFAULT_CSV as CHALLENGE_CSV
from scripts.seed.seed_challenges import parse_rows, read_csv, upsert_challenges
from scripts.seed.seed_rewards import DEFAULT_CSV as REWARD_CSV
from scripts.seed.seed_rewards import seed_rewards

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 7, 21, 0, tzinfo=KST)
PASSWORD = "dango1234"


class TestGlucoBlade(TestCase):
    async def _walking_mission(
        self, email: str, motivation: MotivationType, start: datetime | None = NOW - timedelta(hours=12)
    ) -> UserChallenge:
        await upsert_challenges(parse_rows(read_csv(CHALLENGE_CSV)))
        await seed_rewards(read_csv(REWARD_CSV))
        user = await User.create(email=email, password_hash="x", nickname="t", motivation_type=motivation)
        cycle = await make_cycle(user.id, ["physical_activity_low"])
        walk = await Challenge.get(code="CH_WALK_AFTER_MEAL")
        card = await make_card(user.id, walk, cycle)
        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=user.id, recommendation_ids=[card.id], now=start
        )
        return mission

    async def _walk(self, mission: UserChallenge, slot: str) -> LogResult:
        return await ChallengeCoreService().record_log(
            user_id=mission.user_id,
            user_challenge_id=mission.id,
            occurred_at=NOW - timedelta(hours=1),
            context_slot=slot,
            value=Decimal("10"),
            verification_method=VerificationMethod.TIMER,
            evidence_url=None,
            now=NOW,
        )

    async def test_grow_user_gets_the_blade_once(self) -> None:
        mission = await self._walking_mission("blade-grow@example.com", MotivationType.GROW)

        first = await self._walk(mission, "lunch")
        second = await self._walk(mission, "dinner")

        assert first.reward is not None
        assert first.reward.code == "gluco_blade"
        # 이미 가진 보상은 다시 안내하지 않는다
        assert second.reward is None
        [owned] = await UserReward.filter(user_id=mission.user_id)
        assert owned.item_level == 1
        assert owned.acquired_at == NOW

    async def test_collect_user_gets_nothing(self) -> None:
        mission = await self._walking_mission("blade-collect@example.com", MotivationType.COLLECT)

        result = await self._walk(mission, "lunch")

        assert result.reward is None
        assert await UserReward.filter(user_id=mission.user_id).count() == 0

    async def test_reward_failure_does_not_roll_back_the_log(self) -> None:
        mission = await self._walking_mission("blade-fail@example.com", MotivationType.GROW)

        with patch.object(UserReward, "get_or_create", side_effect=RuntimeError("boom")):
            result = await self._walk(mission, "lunch")

        # 되돌려진 지급은 응답에도 싣지 않는다
        assert result.reward is None
        log = await ChallengeLog.get(user_challenge_id=mission.id)
        assert log.reward_eligible is True
        assert log.xp_granted == 18
        assert (await User.get(id=mission.user_id)).total_xp == 18
        assert await UserReward.filter(user_id=mission.user_id).count() == 0

    async def test_log_response_carries_only_a_new_reward(self) -> None:
        # API 는 실제 시각을 쓰므로 오늘 시작한 미션에 지금 시각으로 기록한다
        mission = await self._walking_mission("blade-api@example.com", MotivationType.GROW, start=None)
        await User.filter(id=mission.user_id).update(password_hash=hash_password(PASSWORD))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login = await client.post(
                "/api/v1/auth/login", json={"email": "blade-api@example.com", "password": PASSWORD}
            )
            headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
            url = f"/api/v1/user-challenges/{mission.id}/logs"
            responses = []
            for slot in ("lunch", "dinner"):
                body = {
                    "occurred_at": datetime.now(KST).isoformat(),
                    "context_slot": slot,
                    "value": 10,
                    "verification_method": "timer",
                }
                responses.append(await client.post(url, json=body, headers=headers))
        first, second = responses

        reward = await Reward.get(code="gluco_blade")
        assert first.json()["data"]["reward"] == {
            "reward_id": reward.id,
            "code": "gluco_blade",
            "name": "글루코 블레이드",
            "reward_kind": "item",
        }
        assert second.json()["data"]["reward"] is None
