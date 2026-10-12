"""사용자 소유 보상 조회. 지급은 기존 수행 기록 서비스가 담당한다."""

from typing import Any

from app.models.challenges import Reward, UserReward


class RewardService:
    async def list_mine(self, user_id: int, page: int, size: int) -> tuple[list[dict[str, Any]], int]:
        """RWRD-01. 소유권을 먼저 제한하고 페이지를 적용한다."""
        query = UserReward.filter(user_id=user_id)
        total = await query.count()
        owned = await query.order_by("-acquired_at", "-id").offset((page - 1) * size).limit(size)
        masters = {reward.id: reward for reward in await Reward.filter(id__in=[item.reward_id for item in owned])}
        return [
            {
                "reward_id": item.reward_id,
                "code": masters[item.reward_id].code,
                "name": masters[item.reward_id].name,
                "motivation_type": masters[item.reward_id].motivation_type,
                "reward_kind": masters[item.reward_id].reward_kind,
                "item_level": item.item_level,
                "acquired_at": item.acquired_at,
            }
            for item in owned
        ], total
