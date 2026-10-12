from datetime import datetime
from typing import Any

from app.core import config
from app.models.challenges import AttackCycleStatus, Monster, MonsterState, UserMonster
from app.services.attack_cycles import TARGETABLE_STATES, AttackCycleService, today_kst
from app.services.challenges import week_start_for


class MonsterService:
    def __init__(self) -> None:
        self.cycles = AttackCycleService()

    async def list_mine(self, user_id: int, now: datetime | None = None) -> list[dict[str, Any]]:
        """MNSTR-01. 현재 draft/active 주기로 대상을 계산하고 시작 전 변경 가능 여부를 전달한다."""
        current = now or datetime.now(config.TIMEZONE)
        await self.cycles.close_expired(user_id, today_kst(current), current)

        monsters = await Monster.filter(is_enabled=True).order_by("no")
        states = {item.monster_id: item for item in await UserMonster.filter(user_id=user_id)}
        cycle = await self.cycles.get_current(user_id)
        target_id = cycle.target_user_monster_id if cycle else None
        this_week = week_start_for(current)

        items = []
        for monster in monsters:
            state = states.get(monster.id)
            # 주간 공략 점수는 월요일 0시 KST 에 초기화된다. 지난주 값은 0 으로 보여준다
            weekly = state.weekly_progress if state and state.progress_week_start == this_week else 0
            items.append(
                {
                    "monster_id": monster.id,
                    "user_monster_id": state.id if state else None,
                    "target_change_allowed": bool(
                        cycle
                        and cycle.status == AttackCycleStatus.DRAFT
                        and state
                        and state.state in TARGETABLE_STATES
                        and state.impact_score is not None
                    ),
                    "code": monster.code,
                    "name": monster.name,
                    "title": monster.title,
                    "disease_scope": monster.disease_scope,
                    "impact_score": state.impact_score if state else None,
                    "state": state.state if state else MonsterState.UNMEASURED,
                    "is_target": state is not None and state.id == target_id,
                    "weekly_progress": weekly,
                    "progress_week_start": state.progress_week_start if state else None,
                    # 28일 누적 진행률 구간은 REQ-RECO-008 이 팀 확정 전이라 값을 만들지 않는다
                    "seal_progress": None,
                    "sealed_at": state.sealed_at if state else None,
                    "seal_count": state.seal_count if state else 0,
                    "reawakened_at": state.reawakened_at if state else None,
                    "impact_source": state.impact_source if state else None,
                }
            )
        return items
