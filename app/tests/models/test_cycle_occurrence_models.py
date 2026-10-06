from datetime import date

import pytest
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError

from app.models.challenges import (
    AttackCycleStatus,
    OccurrenceStatus,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
)


def test_cycle_and_occurrence_use_fixed_table_names() -> None:
    assert UserAttackCycle._meta.db_table == "user_attack_cycles"
    assert UserChallengeOccurrence._meta.db_table == "user_challenge_occurrences"


def test_attack_cycle_status_contract() -> None:
    assert {item.value for item in AttackCycleStatus} == {"draft", "active", "completed", "abandoned"}


def test_occurrence_status_contract() -> None:
    assert {item.value for item in OccurrenceStatus} == {"planned", "completed", "skipped", "missed"}


def test_user_challenge_status_keeps_graduated() -> None:
    # 화면에는 "기간 종료"로 보이지만 저장 값은 graduated 그대로 둔다
    assert "graduated" in {item.value for item in UserChallengeStatus}


def test_user_challenge_has_cycle_and_summary_fields() -> None:
    required = {
        "cycle_id",
        "habit_established",
        "goal_config_snapshot",
        "completed_occurrence_count",
        "planned_occurrence_count",
        "completion_rate",
        "summary_computed_at",
        "summary_policy_version",
    }
    assert required.issubset(UserChallenge._meta.fields_map)
    # 제거안 컬럼은 저장하지 않고 조회할 때 계산한다
    assert "cycle_week" not in UserChallenge._meta.fields_map
    assert "completion_summary_snapshot" not in UserChallenge._meta.fields_map


def test_attack_cycle_does_not_store_derived_columns() -> None:
    # active_user_id 생성 컬럼은 migration raw SQL이 갖는다
    assert "active_user_id" not in UserAttackCycle._meta.fields_map


class TestUserChallengeOccurrence(TestCase):
    async def test_defaults_follow_the_spec(self) -> None:
        occurrence = await UserChallengeOccurrence.create(user_challenge_id=1, scheduled_date=date(2026, 10, 6))

        assert occurrence.slot_code == ""
        assert occurrence.sequence_no == 1
        assert occurrence.status == OccurrenceStatus.PLANNED
        assert occurrence.completed_log_id is None

    async def test_same_opportunity_cannot_be_planned_twice(self) -> None:
        await UserChallengeOccurrence.create(user_challenge_id=2, scheduled_date=date(2026, 10, 6), slot_code="lunch")

        with pytest.raises(IntegrityError):
            await UserChallengeOccurrence.create(
                user_challenge_id=2, scheduled_date=date(2026, 10, 6), slot_code="lunch"
            )

    async def test_one_log_completes_at_most_one_opportunity(self) -> None:
        await UserChallengeOccurrence.create(user_challenge_id=3, scheduled_date=date(2026, 10, 6), completed_log_id=9)

        with pytest.raises(IntegrityError):
            await UserChallengeOccurrence.create(
                user_challenge_id=3, scheduled_date=date(2026, 10, 7), completed_log_id=9
            )


class TestUserChallengeHabitDefault(TestCase):
    async def test_habit_established_defaults_to_unevaluated(self) -> None:
        user_challenge = await UserChallenge.create(
            user_id=1,
            challenge_id=1,
            start_date=date(2026, 10, 6),
            end_date=date(2026, 11, 2),
            daily_target_count_snapshot=1,
            duration_days_snapshot=28,
        )

        # NULL이 미평가다. FALSE를 미형성으로 읽지 않는다
        assert user_challenge.habit_established is None
