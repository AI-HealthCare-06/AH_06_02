"""미션 목표. 시작할 때 한 번 정하고, 그 뒤에는 미션 스냅샷을 기준으로 읽는다."""

from dataclasses import dataclass
from decimal import Decimal

from app.models.challenges import Challenge, UserChallenge


@dataclass(frozen=True)
class Goal:
    target_value: Decimal | None
    daily_target_count: int
    context_slots: list[str]
    difficulty: str
    daily_xp: int


def master_goal(challenge: Challenge) -> Goal:
    """마스터 고정 원형 목표."""
    return Goal(
        target_value=challenge.target_value,
        daily_target_count=challenge.daily_target_count,
        context_slots=list(challenge.context_slots or []),
        difficulty=str(challenge.difficulty),
        daily_xp=challenge.reward_xp,
    )


def mission_slots(mission: UserChallenge, challenge: Challenge) -> list[str]:
    """진행 중 미션의 식사 슬롯."""
    return list(challenge.context_slots or [])
