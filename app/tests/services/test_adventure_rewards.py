from datetime import datetime
from unittest.mock import patch

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
from app.services.adventure_catalog import CATALOG
from app.services.adventure_rewards import RANDOM, AdventureRewardService, draw_body


class TestAdventureRewards(TestCase):
    async def prepare(self, user: User | None = None) -> tuple[User, RewardDraw]:
        user = user or await User.create(email="draw@example.com", password_hash="x", nickname="보상 검증")
        challenge = await Challenge.create(
            code=f"DRAW-{await Challenge.all().count()}",
            title="보상 검증",
            category=ChallengeCategory.ACTIVITY,
            goal_type=GoalType.BOOLEAN,
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

    async def test_claim_takes_one_card_and_replay_does_not_grant_twice(self) -> None:
        user, draw = await self.prepare()
        service = AdventureRewardService()
        result = await service.claim(user.id, draw.id, [3])
        assert [item["code"] for item in result["results"]] == ["material"]
        # 조각 카드는 RARE 재료이며 조각 2개를 준다
        assert result["results"][0]["rarity"] == "RARE"
        assert result["results"][0]["materials"] == 2
        assert await service.claim(user.id, draw.id, [3]) == result
        with self.assertRaises(AppError):
            await service.claim(user.id, draw.id, [2])
        assert (await service.state(user.id)).materials == 2

    async def test_duplicate_card_turns_into_materials_by_rarity(self) -> None:
        user, draw = await self.prepare()
        service = AdventureRewardService()
        await service.claim(user.id, draw.id, [0])
        _, second = await self.prepare(user)
        duplicate = await service.claim(user.id, second.id, [1])
        assert duplicate["results"][0]["duplicate"] is True
        assert duplicate["results"][0]["materials"] == 2
        await service.update(user.id, {"hat": "explorer-hat"}, {})
        assert (await service.state(user.id)).equipment["hat"] == "explorer-hat"

    async def test_other_user_and_invalid_positions_cannot_receive_draw(self) -> None:
        user, draw = await self.prepare()
        stranger = await User.create(email="other@example.com", password_hash="x", nickname="다른 계정")
        service = AdventureRewardService()
        invalid: list[list[int]] = [[], [0, 1], [0, 1, 2], [5], [-1], [True]]
        for positions in invalid:
            with self.assertRaises(AppError):
                await service.claim(user.id, draw.id, positions)
        with self.assertRaises(AppError):
            await service.claim(stranger.id, draw.id, [0])
        assert (await RewardDraw.get(id=draw.id)).claimed_at is None
        assert draw_body(draw)["results"] is None

    async def test_rare_cards_appear_at_fifteen_percent_and_material_is_rare(self) -> None:
        user, _ = await self.prepare()
        logs = []
        for _ in range(2):
            # 뽑기는 수행 기록당 하나라 새 기록을 비워 둔다
            _, made = await self.prepare(user)
            logs.append(made.challenge_log_id)
            await made.delete()
        rare = {entry["code"] for entry in CATALOG if entry["rarity"] == "RARE" and not entry["starter"]}
        common = {entry["code"] for entry in CATALOG if entry["rarity"] == "COMMON" and not entry["starter"]}
        assert "material" in rare and "material" not in common
        with patch.object(RANDOM, "random", return_value=0.149):
            assert set((await AdventureRewardService().create_draw(user.id, logs[0])).cards) <= rare
        with patch.object(RANDOM, "random", return_value=0.15):
            assert set((await AdventureRewardService().create_draw(user.id, logs[1])).cards) <= common

    async def test_each_stage_needs_more_materials(self) -> None:
        user, _ = await self.prepare()
        service = AdventureRewardService()
        state = await service.state(user.id)
        # 2단계는 조각 20개, 3단계는 조각 40개
        await AdventurerState.filter(id=state.id).update(materials=19)
        with self.assertRaises(AppError):
            await service.upgrade(user.id)
        await AdventurerState.filter(id=state.id).update(materials=20)
        assert (await service.upgrade(user.id))["item_stage"] == 2
        await AdventurerState.filter(id=state.id).update(materials=39)
        with self.assertRaises(AppError):
            await service.upgrade(user.id)
        await AdventurerState.filter(id=state.id).update(materials=45)
        upgraded = await service.upgrade(user.id)
        assert (upgraded["item_stage"], upgraded["materials"]) == (3, 5)
        await AdventurerState.filter(id=state.id).update(materials=100)
        with self.assertRaises(AppError):
            await service.upgrade(user.id)
        assert (await service.state(user.id)).materials == 100

    async def test_slot_validation_is_atomic(self) -> None:
        user, _ = await self.prepare()
        service = AdventureRewardService()
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
