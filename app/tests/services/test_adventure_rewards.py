from datetime import datetime

from tortoise.contrib.test import TestCase

from app.core import config
from app.core.errors import AppError
from app.models.challenges import (
    AdventurerState,
    Challenge,
    ChallengeCategory,
    ChallengeLog,
    GoalType,
    RewardDraw,
    UserChallenge,
    UserChallengeStatus,
)
from app.models.users import User
from app.services.adventure_rewards import AdventureRewardService, draw_body


class TestAdventureRewards(TestCase):
    async def prepare(self) -> tuple[User, RewardDraw]:
        user = await User.create(email="draw@example.com", password_hash="x", nickname="보상 검증")
        challenge = await Challenge.create(
            code="DRAW", title="보상 검증", category=ChallengeCategory.ACTIVITY, goal_type=GoalType.BOOLEAN
        )
        day = datetime.now(config.TIMEZONE).date()
        mission = await UserChallenge.create(
            user_id=user.id,
            challenge_id=challenge.id,
            status=UserChallengeStatus.ACTIVE,
            start_date=day,
            end_date=day,
            daily_target_count_snapshot=1,
            duration_days_snapshot=1,
        )
        log = await ChallengeLog.create(
            user_challenge_id=mission.id, log_date=day, occurred_at=datetime.now(config.TIMEZONE)
        )
        return user, await RewardDraw.create(
            user_id=user.id,
            challenge_log_id=log.id,
            cards=["explorer-hat", "explorer-hat", "magic-syringe", "material", "night"],
        )

    async def test_claim_replay_does_not_grant_twice_and_rejects_changed_selection(self) -> None:
        user, draw = await self.prepare()
        service = AdventureRewardService()
        result = await service.claim(user.id, draw.id, [2, 0, 1])
        assert result["results"][0]["duplicate"] is False
        assert result["results"][1]["duplicate"] is True
        assert result["results"][1]["materials"] == 2
        replay = await service.claim(user.id, draw.id, [1, 2, 0])
        assert replay == result
        assert (await service.state(user.id)).materials == 2
        with self.assertRaises(AppError):
            await service.claim(user.id, draw.id, [1, 2, 3])
        assert (await service.state(user.id)).materials == 2
        await service.update(user.id, {"hat": "explorer-hat", "hand": "magic-syringe"}, {})
        assert (await service.state(user.id)).equipment["hat"] == "explorer-hat"

    async def test_other_user_and_invalid_positions_cannot_receive_draw(self) -> None:
        user, draw = await self.prepare()
        stranger = await User.create(email="other@example.com", password_hash="x", nickname="다른 계정")
        service = AdventureRewardService()
        for positions in ([0, 0, 1], [0, 1], [0, 1, 5], [True, 1, 2]):
            with self.assertRaises(AppError):
                await service.claim(user.id, draw.id, positions)
        with self.assertRaises(AppError):
            await service.claim(stranger.id, draw.id, [0, 1, 2])
        assert (await RewardDraw.get(id=draw.id)).claimed_at is None
        assert draw_body(draw)["results"] is None

    async def test_materials_upgrade_and_slot_validation_are_atomic(self) -> None:
        user, draw = await self.prepare()
        service = AdventureRewardService()
        await service.claim(user.id, draw.id, [0, 2, 3])
        state = await service.state(user.id)
        assert state.materials == 1
        with self.assertRaises(AppError):
            await service.upgrade(user.id)
        await AdventurerState.filter(id=state.id).update(materials=10)
        assert (await service.upgrade(user.id))["item_stage"] == 2
        assert (await service.upgrade(user.id))["materials"] == 0
        await AdventurerState.filter(id=state.id).update(materials=10)
        with self.assertRaises(AppError):
            await service.upgrade(user.id)
        assert (await service.state(user.id)).materials == 10
        for equipment, room in [
            ({"hat": "magic-syringe"}, {}),
            ({"hair": "explorer-hat"}, {}),
            ({}, {"bed": "unknown"}),
            ({}, {"chair": "room-cloud-chair"}),
        ]:
            with self.assertRaises(AppError):
                await service.update(user.id, equipment, room)
        assert (await service.state(user.id)).equipment == {}
        await service.update(user.id, {"hat": None}, {"bed": None})
        assert (await service.state(user.id)).room["bed"] is None
