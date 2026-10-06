from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from tortoise.contrib.test import TestCase

from app.models.challenges import Challenge, ChallengeLog, UserChallenge, UserReward, VerificationMethod
from app.models.users import MotivationType, User
from app.services.challenges import ChallengeCoreService
from app.tests.d_fixtures import make_card, make_cycle
from scripts.seed.seed_challenges import DEFAULT_CSV as CHALLENGE_CSV
from scripts.seed.seed_challenges import parse_rows, read_csv, upsert_challenges
from scripts.seed.seed_rewards import DEFAULT_CSV as REWARD_CSV
from scripts.seed.seed_rewards import seed_rewards

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 7, 21, 0, tzinfo=KST)


class TestGlucoBlade(TestCase):
    async def _walking_mission(self, email: str, motivation: MotivationType) -> UserChallenge:
        await upsert_challenges(parse_rows(read_csv(CHALLENGE_CSV)))
        await seed_rewards(read_csv(REWARD_CSV))
        user = await User.create(email=email, password_hash="x", nickname="t", motivation_type=motivation)
        cycle = await make_cycle(user.id, ["physical_activity_low"])
        walk = await Challenge.get(code="CH_WALK_AFTER_MEAL")
        card = await make_card(user.id, walk, cycle)
        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=user.id, recommendation_ids=[card.id], now=NOW - timedelta(hours=12)
        )
        return mission

    async def _walk(self, mission: UserChallenge, slot: str) -> None:
        await ChallengeCoreService().record_log(
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

        await self._walk(mission, "lunch")
        await self._walk(mission, "dinner")

        [owned] = await UserReward.filter(user_id=mission.user_id)
        assert owned.item_level == 1
        assert owned.acquired_at == NOW

    async def test_collect_user_gets_nothing(self) -> None:
        mission = await self._walking_mission("blade-collect@example.com", MotivationType.COLLECT)

        await self._walk(mission, "lunch")

        assert await UserReward.filter(user_id=mission.user_id).count() == 0

    async def test_reward_failure_does_not_roll_back_the_log(self) -> None:
        mission = await self._walking_mission("blade-fail@example.com", MotivationType.GROW)

        with patch.object(UserReward, "get_or_create", side_effect=RuntimeError("boom")):
            await self._walk(mission, "lunch")

        log = await ChallengeLog.get(user_challenge_id=mission.id)
        assert log.reward_eligible is True
        assert log.xp_granted == 18
        assert (await User.get(id=mission.user_id)).total_xp == 18
        assert await UserReward.filter(user_id=mission.user_id).count() == 0
