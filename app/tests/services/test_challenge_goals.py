"""개인 목표 단계표가 마스터 고정 원형과 어긋나지 않는지 확인한다."""

from decimal import Decimal

import pytest

from app.models.challenges import Challenge
from app.services.challenge_goals import PolicyError, goal_policy, validate_policy
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv


def master_challenges() -> dict[str, Challenge]:
    return {str(values["code"]): Challenge(**values) for values in parse_rows(read_csv(DEFAULT_CSV))}


def test_every_master_policy_keeps_the_fixed_goal_as_its_base_step() -> None:
    challenges = master_challenges()
    for challenge in challenges.values():
        validate_policy(challenge)

    walk = goal_policy(challenges["CH_WALK_AFTER_MEAL"])
    assert walk is not None
    base = walk.step(walk.base_level)
    assert base is not None
    # 마스터: 식후 걷기 10분, 점심·저녁 2회, challenge
    assert (base.target_value, base.daily_target_count, base.context_slots, base.difficulty) == (
        Decimal("10"),
        2,
        ["lunch", "dinner"],
        "challenge",
    )


def _walk_with(steps: list[dict[str, object]], *, status: str = "approved", base_level: int = 1) -> Challenge:
    walk = master_challenges()["CH_WALK_AFTER_MEAL"]
    base = {"level": 1, "title": "식후 걷기", "target_value": 10, "daily_target_count": 2}
    walk.personalization_policy = {
        "version": "t",
        "status": status,
        "base_level": base_level,
        "steps": [{**base, "context_slots": ["lunch", "dinner"], "difficulty": "challenge"}, *steps],
    }
    return walk


@pytest.mark.parametrize(
    "step",
    [
        # 단계 번호가 비었다
        {"level": 3, "title": "식후 걷기", "target_value": 10, "daily_target_count": 2, "difficulty": "challenge"},
        # 마스터에 없는 아침 슬롯
        {
            "level": 2,
            "title": "식후 걷기",
            "target_value": 10,
            "daily_target_count": 1,
            "context_slots": ["breakfast"],
            "difficulty": "challenge",
        },
        # 슬롯 두 개인데 하루 1회
        {
            "level": 2,
            "title": "식후 걷기",
            "target_value": 10,
            "daily_target_count": 1,
            "context_slots": ["lunch", "dinner"],
            "difficulty": "challenge",
        },
        # 위 단계가 아래 단계보다 쉬운 난이도
        {
            "level": 2,
            "title": "식후 걷기",
            "target_value": 15,
            "daily_target_count": 2,
            "context_slots": ["lunch", "dinner"],
            "difficulty": "easy",
        },
    ],
)
def test_step_outside_the_master_shape_is_refused(step: dict[str, object]) -> None:
    with pytest.raises(PolicyError):
        validate_policy(_walk_with([step]))


def test_policy_before_approval_is_not_used() -> None:
    walk = _walk_with([], status="draft")

    validate_policy(walk)
    assert goal_policy(walk) is None
