"""미션 목표. 시작할 때 한 번 정하고, 그 뒤에는 미션 스냅샷을 기준으로 읽는다.

개인 목표는 challenges.personalization_policy 의 승인된 단계표 안에서만 고른다.
기본 단계는 마스터 고정 원형과 같고, 하루 XP 는 단계 난이도로 서버가 정한다 (10/6 A·D 합의).
"""

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.errors import AppError, ErrorCode
from app.models.challenges import Challenge, UserChallenge

#: 난이도별 하루 총 XP (docs/01_planning/challenge-candidates.md)
DIFFICULTY_XP = {"easy": 12, "normal": 24, "challenge": 36}
DIFFICULTY_ORDER = tuple(DIFFICULTY_XP)
APPROVED = "approved"
#: 다음 주기 단계 기준. 지난 주기 수행률(인정 완료 ÷ 예정 기회)로만 정한다
RAISE_AT = Decimal("0.8")
KEEP_AT = Decimal("0.5")
STALE_GOAL_MESSAGE = "개인 목표가 지금 단계표와 맞지 않아요. 추천을 다시 받아 주세요."


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class GoalStep:
    level: int
    title: str
    target_value: Decimal | None
    daily_target_count: int
    context_slots: list[str]
    intensity: str | None
    difficulty: str


@dataclass(frozen=True)
class GoalPolicy:
    version: str
    status: str
    base_level: int
    steps: tuple[GoalStep, ...]

    def step(self, level: int) -> GoalStep | None:
        return next((item for item in self.steps if item.level == level), None)

    @property
    def lowest(self) -> int:
        return self.steps[0].level

    @property
    def highest(self) -> int:
        return self.steps[-1].level


@dataclass(frozen=True)
class Goal:
    target_value: Decimal | None
    daily_target_count: int
    context_slots: list[str]
    difficulty: str
    daily_xp: int
    #: 아래 값은 단계표가 있는 챌린지만 채운다
    title: str | None = None
    intensity: str | None = None
    level: int | None = None
    policy_version: str | None = None
    basis: dict[str, Any] | None = None
    #: 지난 단계보다 올린 목표. 시작할 때 안전 확인을 다시 받는다
    raised: bool = False


def master_goal(challenge: Challenge) -> Goal:
    """마스터 고정 원형 목표."""
    return Goal(
        target_value=challenge.target_value,
        daily_target_count=challenge.daily_target_count,
        context_slots=list(challenge.context_slots or []),
        difficulty=str(challenge.difficulty),
        daily_xp=challenge.reward_xp,
    )


def step_goal(policy: GoalPolicy, step: GoalStep, basis: dict[str, Any] | None = None) -> Goal:
    previous = (basis or {}).get("previous_level")
    return Goal(
        target_value=step.target_value,
        daily_target_count=step.daily_target_count,
        context_slots=list(step.context_slots),
        difficulty=step.difficulty,
        daily_xp=DIFFICULTY_XP[step.difficulty],
        title=step.title,
        intensity=step.intensity,
        level=step.level,
        policy_version=policy.version,
        basis=basis,
        raised=isinstance(previous, int) and step.level > previous,
    )


def proposed_step(challenge: Challenge, proposed_goal: Any) -> tuple[GoalPolicy, GoalStep]:
    """추천 카드의 개인 목표를 지금 단계표에서 다시 찾는다. 맞지 않으면 시작하지 않는다."""
    policy = goal_policy(challenge)
    if policy is None or not isinstance(proposed_goal, dict) or proposed_goal.get("policy_version") != policy.version:
        raise AppError(ErrorCode.VALIDATION_ERROR, message=STALE_GOAL_MESSAGE)
    level = proposed_goal.get("level")
    step = policy.step(level) if isinstance(level, int) else None
    if step is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, message=STALE_GOAL_MESSAGE)
    return policy, step


def start_goal(challenge: Challenge, proposed_goal: Any) -> Goal:
    """시작할 때 확정할 목표. 개인 목표가 없으면 고정 원형이고, 단계표가 있으면 기본 단계로 기록한다."""
    if proposed_goal is None:
        policy = goal_policy(challenge)
        base = policy.step(policy.base_level) if policy else None
        if policy is None or base is None:
            return master_goal(challenge)
        # 고정 원형으로 시작한 미션의 XP 는 지금처럼 마스터 값을 쓴다
        return replace(step_goal(policy, base), daily_xp=challenge.reward_xp)
    policy, step = proposed_step(challenge, proposed_goal)
    basis = proposed_goal.get("basis")
    return step_goal(policy, step, basis if isinstance(basis, dict) else None)


def display_goal(challenge: Challenge, proposed_goal: Any) -> Goal:
    """추천 카드에 보여 줄 목표. 단계표가 바뀐 옛 카드는 고정 원형을 보여 주고, 시작할 때 거부된다."""
    try:
        return start_goal(challenge, proposed_goal)
    except AppError:
        return master_goal(challenge)


def goal_snapshot(goal: Goal) -> dict[str, Any]:
    """goal_config_snapshot 에 더할 단계 값. 단계표가 없는 챌린지는 비어 있다."""
    if goal.level is None:
        return {}
    snapshot: dict[str, Any] = {
        "level": goal.level,
        "policy_version": goal.policy_version,
        "title": goal.title,
        "intensity": goal.intensity,
        "context_slots": goal.context_slots,
    }
    if goal.basis is not None:
        snapshot["basis"] = goal.basis
    return snapshot


@dataclass(frozen=True)
class NextStep:
    level: int
    direction: str
    #: 가장 낮은 단계에서도 절반을 못 채웠다. 다른 챌린지를 먼저 보여 준다
    defer: bool = False


def next_step(policy: GoalPolicy, previous_level: int, completion_rate: Decimal) -> NextStep:
    """80% 이상 한 단계 위, 50% 이상 80% 미만 유지, 50% 미만 한 단계 아래. 끝 단계에서는 머문다."""
    if completion_rate >= RAISE_AT:
        level = min(previous_level + 1, policy.highest)
    elif completion_rate >= KEEP_AT:
        level = previous_level
    else:
        if previous_level <= policy.lowest:
            return NextStep(level=policy.lowest, direction="keep", defer=True)
        level = previous_level - 1
    direction = "up" if level > previous_level else "down" if level < previous_level else "keep"
    return NextStep(level=level, direction=direction)


def mission_slots(mission: UserChallenge, challenge: Challenge) -> list[str]:
    """진행 중 미션의 식사 슬롯. 단계 목표는 스냅샷이 원본이고, 레거시 행은 마스터를 따른다."""
    slots = (mission.goal_config_snapshot or {}).get("context_slots")
    if isinstance(slots, list):
        return [str(slot) for slot in slots]
    return list(challenge.context_slots or [])


def mission_title(mission: UserChallenge, challenge: Challenge) -> str:
    title = (mission.goal_config_snapshot or {}).get("title")
    return title if isinstance(title, str) and title else challenge.title


def mission_level(mission: UserChallenge, policy: GoalPolicy) -> int:
    """미션이 쓴 단계. 단계 기록이 없거나 지금 단계표에 없는 미션은 기본 단계로 본다."""
    snapshot = mission.goal_config_snapshot or {}
    level = snapshot.get("level")
    if snapshot.get("policy_version") == policy.version and isinstance(level, int) and policy.step(level):
        return level
    return policy.base_level


def _parse_step(raw: Any) -> GoalStep:
    if not isinstance(raw, dict):
        raise PolicyError("단계는 객체여야 합니다.")
    try:
        target = raw.get("target_value")
        slots = raw.get("context_slots") or []
        step = GoalStep(
            level=int(raw["level"]),
            title=str(raw["title"]),
            target_value=None if target is None else Decimal(str(target)),
            daily_target_count=int(raw["daily_target_count"]),
            context_slots=[str(slot) for slot in slots],
            intensity=None if raw.get("intensity") is None else str(raw["intensity"]),
            difficulty=str(raw["difficulty"]),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise PolicyError(f"단계 값을 해석할 수 없습니다: {raw!r}") from exc
    if not isinstance(slots, list):
        raise PolicyError("context_slots 는 목록이어야 합니다.")
    return step


def parse_policy(raw: Any) -> GoalPolicy | None:
    """personalization_policy JSON 을 읽는다. NULL 은 고정 원형이다. 승인 여부는 따지지 않는다."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list) or not raw["steps"]:
        raise PolicyError("personalization_policy 에는 version·status·base_level·steps 가 있어야 합니다.")
    try:
        version, status, base_level = str(raw["version"]), str(raw["status"]), int(raw["base_level"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PolicyError("version·status·base_level 을 해석할 수 없습니다.") from exc
    steps = tuple(sorted((_parse_step(item) for item in raw["steps"]), key=lambda item: item.level))
    return GoalPolicy(version=version, status=status, base_level=base_level, steps=steps)


def goal_policy(challenge: Challenge) -> GoalPolicy | None:
    """운영에 쓰는 단계표. 정책이 없거나 승인 전이면 None 이고 고정 원형만 쓴다."""
    policy = parse_policy(challenge.personalization_policy)
    if policy is None or policy.status != APPROVED:
        return None
    return policy


def validate_policy(challenge: Challenge) -> None:
    """단계표가 마스터와 어긋나면 PolicyError. 시드가 쓰기 전에 부른다."""
    policy = parse_policy(challenge.personalization_policy)
    if policy is None:
        return
    code = challenge.code
    levels = [step.level for step in policy.steps]
    if levels != list(range(1, len(levels) + 1)):
        raise PolicyError(f"{code}: 단계 번호는 1부터 빠짐없이 이어져야 합니다 ({levels}).")
    base = policy.step(policy.base_level)
    if base is None:
        raise PolicyError(f"{code}: base_level {policy.base_level} 단계가 없습니다.")
    master = master_goal(challenge)
    if (base.title, base.target_value, base.daily_target_count, base.context_slots, base.difficulty) != (
        challenge.title,
        master.target_value,
        master.daily_target_count,
        master.context_slots,
        master.difficulty,
    ) or (base.intensity is not None):
        raise PolicyError(f"{code}: 기본 단계는 마스터 고정 원형과 같아야 합니다.")
    previous_rank = -1
    for step in policy.steps:
        if step.difficulty not in DIFFICULTY_XP:
            raise PolicyError(f"{code}: {step.level}단계 난이도 {step.difficulty} 를 모릅니다.")
        rank = DIFFICULTY_ORDER.index(step.difficulty)
        if rank < previous_rank:
            raise PolicyError(f"{code}: 단계가 오를수록 난이도가 낮아지면 안 됩니다.")
        previous_rank = rank
        _check_step(code, step, master)


def _check_step(code: str, step: GoalStep, master: Goal) -> None:
    if not step.title or len(step.title) > 80:
        raise PolicyError(f"{code}: {step.level}단계 제목이 비었거나 깁니다.")
    if step.daily_target_count < 1:
        raise PolicyError(f"{code}: {step.level}단계 하루 횟수는 1 이상이어야 합니다.")
    if (step.target_value is None) != (master.target_value is None):
        raise PolicyError(f"{code}: {step.level}단계 목표값 유무가 마스터와 다릅니다.")
    if step.target_value is not None and step.target_value <= 0:
        raise PolicyError(f"{code}: {step.level}단계 목표값은 0보다 커야 합니다.")
    if not set(step.context_slots) <= set(master.context_slots) or len(set(step.context_slots)) != len(
        step.context_slots
    ):
        raise PolicyError(f"{code}: {step.level}단계 슬롯은 마스터 슬롯 안에서 겹치지 않게 고릅니다.")
    if step.context_slots and len(step.context_slots) != step.daily_target_count:
        raise PolicyError(f"{code}: {step.level}단계 하루 횟수와 슬롯 수가 맞지 않습니다.")
