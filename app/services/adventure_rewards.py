"""인정 수행의 통합 보상과 모험가·방 상태를 원자적으로 저장한다."""

from collections.abc import Mapping
from datetime import datetime
from random import SystemRandom
from typing import Any

from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import AdventurerState, Reward, RewardDraw, RewardKind, RewardMotivationType, UserReward
from app.services.adventure_catalog import BASIC_ROOM, BY_CODE, CATALOG, EQUIPMENT_SLOTS, ROOM_SLOTS
from app.services.attack_cycles import lock_user

RANDOM = SystemRandom()


def state_body(state: AdventurerState) -> dict[str, Any]:
    return {
        "equipment": state.equipment,
        "room": {**BASIC_ROOM, **state.room},
        "materials": state.materials,
        "item_stage": state.item_stage,
    }


def draw_body(draw: RewardDraw) -> dict[str, Any]:
    return {
        "draw_id": draw.id,
        "challenge_log_id": draw.challenge_log_id,
        "card_count": 5,
        "claimed_at": draw.claimed_at,
        "selected_positions": draw.selected_positions,
        "results": draw.results,
    }


class AdventureRewardService:
    async def state(self, user_id: int) -> AdventurerState:
        state, _ = await AdventurerState.get_or_create(user_id=user_id)
        return state

    async def catalog(self, user_id: int) -> dict[str, Any]:
        state = await self.state(user_id)
        rewards = await Reward.filter(
            id__in=await UserReward.filter(user_id=user_id).values_list("reward_id", flat=True)
        )
        owned = {reward.code for reward in rewards}
        return {
            "items": [{**entry, "owned": entry["starter"] or entry["code"] in owned} for entry in CATALOG],
            "materials": state.materials,
            "item_stage": state.item_stage,
        }

    async def create_draw(self, user_id: int, log_id: int) -> RewardDraw:
        """수행 기록 트랜잭션과 사용자 잠금 안에서만 호출한다."""
        pool = [entry for entry in CATALOG if not entry["starter"]]
        cards = []
        for _ in range(5):
            rarity = "RARE" if RANDOM.random() < 0.25 else "COMMON"
            cards.append(RANDOM.choice([entry["code"] for entry in pool if entry["rarity"] == rarity]))
        return await RewardDraw.create(user_id=user_id, challenge_log_id=log_id, cards=cards)

    async def claim(self, user_id: int, draw_id: int, positions: list[int]) -> dict[str, Any]:
        if (
            len(positions) != 3
            or len(set(positions)) != 3
            or any(type(p) is not int or not 0 <= p < 5 for p in positions)
        ):
            raise AppError(ErrorCode.VALIDATION_ERROR, message="카드 5장 중 서로 다른 3장을 골라주세요.")
        positions = sorted(positions)
        async with in_transaction():
            await lock_user(user_id)
            draw = await RewardDraw.select_for_update().get_or_none(id=draw_id, user_id=user_id)
            if draw is None:
                raise AppError(ErrorCode.CHLG_NOT_FOUND)
            if draw.claimed_at is not None:
                if positions != draw.selected_positions:
                    raise AppError(ErrorCode.VALIDATION_ERROR, message="이미 선택한 보상을 받았어요.")
                return draw_body(draw)
            state = await self.state(user_id)
            receipts = [await self._grant(user_id, BY_CODE[draw.cards[position]], state) for position in positions]
            await state.save(update_fields=["materials", "updated_at"])
            draw.selected_positions, draw.results, draw.claimed_at = positions, receipts, datetime.now(config.TIMEZONE)
            await draw.save(update_fields=["selected_positions", "results", "claimed_at", "updated_at"])
            return draw_body(draw)

    @staticmethod
    async def _grant(user_id: int, entry: dict[str, Any], state: AdventurerState) -> dict[str, Any]:
        duplicate, materials = False, 0
        if entry["code"] == "material":
            materials = 1
        else:
            reward, _ = await Reward.get_or_create(
                code=entry["code"],
                defaults={
                    "name": entry["name"],
                    "motivation_type": RewardMotivationType.COLLECT,
                    "reward_kind": RewardKind.ITEM,
                    "unlock_condition": "인정 수행 보상 카드에서 획득",
                },
            )
            _, created = await UserReward.get_or_create(
                user_id=user_id, reward_id=reward.id, defaults={"acquired_at": datetime.now(config.TIMEZONE)}
            )
            duplicate = not created
            if duplicate:
                materials = 3 if entry["rarity"] == "RARE" else 2
        state.materials += materials
        return {**entry, "duplicate": duplicate, "materials": materials}

    async def update(
        self, user_id: int, equipment: Mapping[str, str | None], room: Mapping[str, str | None]
    ) -> dict[str, Any]:
        async with in_transaction():
            await lock_user(user_id)
            catalog = {entry["code"]: entry for entry in (await self.catalog(user_id))["items"]}
            for values, slots in ((equipment, EQUIPMENT_SLOTS), (room, ROOM_SLOTS)):
                for slot, code in values.items():
                    if slot not in slots or (
                        code is not None
                        and (code not in catalog or catalog[code]["slot"] != slot or not catalog[code]["owned"])
                    ):
                        raise AppError(ErrorCode.VALIDATION_ERROR, message="획득한 아이템을 맞는 위치에 적용해주세요.")
            state = await self.state(user_id)
            state.equipment = {**state.equipment, **equipment}
            state.room = {**state.room, **room}
            await state.save(update_fields=["equipment", "room", "updated_at"])
            return state_body(state)

    async def upgrade(self, user_id: int) -> dict[str, Any]:
        async with in_transaction():
            await lock_user(user_id)
            state = await self.state(user_id)
            if state.materials < 5 or state.item_stage >= 3:
                raise AppError(ErrorCode.VALIDATION_ERROR, message="성장의 조각 5개가 필요해요. 최대 단계는 3단계예요.")
            state.materials -= 5
            state.item_stage += 1
            await state.save(update_fields=["materials", "item_stage", "updated_at"])
            return state_body(state)
