from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError

from app.core import config
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeCategory,
    ChallengeRecommendation,
    GoalType,
    OccurrenceStatus,
    RecommendationSourceType,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
)


async def _mission(**overrides: Any) -> UserChallenge:
    values: dict[str, Any] = {
        "user_id": 1,
        "challenge_id": 1,
        "start_date": date(2026, 10, 6),
        "end_date": date(2026, 11, 2),
        "daily_target_count_snapshot": 1,
        "duration_days_snapshot": 28,
    }
    return await UserChallenge.create(**(values | overrides))


class TestDCyclePersistence(TestCase):
    async def test_draft_keeps_dates_unset_until_start(self) -> None:
        cycle = await UserAttackCycle.create(user_id=1, target_user_monster_id=1, policy_version="TEST-POLICY")
        saved = await UserAttackCycle.get(id=cycle.id)

        assert saved.status == AttackCycleStatus.DRAFT
        assert saved.start_date is None
        assert saved.end_date is None
        assert saved.extra_added_count == 0

    async def test_period_end_does_not_assign_a_habit_verdict(self) -> None:
        mission = await _mission(status=UserChallengeStatus.GRADUATED)
        saved = await UserChallenge.get(id=mission.id)

        assert saved.status == UserChallengeStatus.GRADUATED
        assert saved.habit_established is None
        assert saved.cycle_id is None
        assert saved.goal_config_snapshot is None
        assert saved.completed_occurrence_count is None
        assert saved.planned_occurrence_count is None
        assert saved.completion_rate is None
        assert saved.summary_computed_at is None
        assert saved.summary_policy_version is None

    async def test_summary_and_goal_snapshot_survive_round_trip(self) -> None:
        cycle = await UserAttackCycle.create(
            user_id=1,
            target_user_monster_id=1,
            policy_version="TEST-POLICY",
            status=AttackCycleStatus.ACTIVE,
            start_date=date(2026, 10, 6),
            end_date=date(2026, 11, 2),
        )
        snapshot = {"slots": ["lunch"], "policy_version": "TEST-POLICY"}
        computed_at = datetime(2026, 11, 2, 15, tzinfo=config.TIMEZONE)
        mission = await _mission(
            cycle_id=cycle.id,
            goal_config_snapshot=snapshot,
            completed_occurrence_count=9,
            planned_occurrence_count=28,
            completion_rate=Decimal("0.3214"),
            summary_computed_at=computed_at,
            summary_policy_version="TEST-SUMMARY",
        )
        saved = await UserChallenge.get(id=mission.id)

        assert saved.cycle_id == cycle.id
        assert saved.goal_config_snapshot == snapshot
        assert saved.completed_occurrence_count == 9
        assert saved.planned_occurrence_count == 28
        assert saved.completion_rate == Decimal("0.3214")
        assert saved.summary_computed_at == computed_at
        assert saved.summary_policy_version == "TEST-SUMMARY"

    async def test_kst_calendar_date_is_preserved_and_empty_slot_is_unique(self) -> None:
        # Preserve the KST calendar date.
        scheduled_date = datetime(2026, 10, 6, tzinfo=config.TIMEZONE).date()
        row = await UserChallengeOccurrence.create(user_challenge_id=1, scheduled_date=scheduled_date)
        saved = await UserChallengeOccurrence.get(id=row.id)

        assert saved.scheduled_date == date(2026, 10, 6)
        assert saved.slot_code == ""
        assert saved.sequence_no == 1
        assert saved.status == OccurrenceStatus.PLANNED
        assert saved.completed_log_id is None
        with pytest.raises(IntegrityError):
            await UserChallengeOccurrence.create(user_challenge_id=1, scheduled_date=scheduled_date)

    async def test_meal_slots_and_independent_sequences_do_not_collide(self) -> None:
        for slot, sequence in (("lunch", 1), ("dinner", 1), ("", 1), ("", 2)):
            await UserChallengeOccurrence.create(
                user_challenge_id=1,
                scheduled_date=date(2026, 10, 6),
                slot_code=slot,
                sequence_no=sequence,
            )
        assert await UserChallengeOccurrence.filter(user_challenge_id=1).count() == 4

        with pytest.raises(IntegrityError):
            await UserChallengeOccurrence.create(
                user_challenge_id=1, scheduled_date=date(2026, 10, 6), slot_code="lunch"
            )

    async def test_occurrence_statuses_survive_round_trip(self) -> None:
        for sequence, status in enumerate(OccurrenceStatus, start=1):
            row = await UserChallengeOccurrence.create(
                user_challenge_id=1,
                scheduled_date=date(2026, 10, 6),
                sequence_no=sequence,
                status=status,
            )
            assert (await UserChallengeOccurrence.get(id=row.id)).status == status

    async def test_conversation_fields_and_fixed_master_defaults(self) -> None:
        master = await Challenge.create(code="TEST-FIXED", title="Test", category="activity", goal_type="duration")
        saved_master = await Challenge.get(id=master.id)
        assert saved_master.context_priority is None
        assert saved_master.personalization_policy is None

        policy = {"version": "TEST-POLICY", "allowed_goals": [{"minutes": 5, "slots": ["lunch"]}]}
        personalized = await Challenge.create(
            code="TEST-PERSONAL",
            title="Test",
            category=ChallengeCategory.ACTIVITY,
            goal_type=GoalType.DURATION,
            context_priority=1,
            personalization_policy=policy,
        )
        reloaded = await Challenge.get(id=personalized.id)
        assert reloaded.context_priority == 1
        assert reloaded.personalization_policy == policy

        recommendation = await ChallengeRecommendation.create(
            user_id=1,
            challenge_id=personalized.id,
            cycle_id=1,
            source_type=RecommendationSourceType.CONVERSATION,
            factor_key="physical_activity_low",
            rank=1,
            recommended_at=datetime(2026, 10, 6, tzinfo=config.TIMEZONE),
            conversation_snapshot={"answers": ["lunch"]},
            llm_model_version="TEST-MODEL",
            evidence_card_ids=["TEST-CARD"],
            proposed_goal={"slots": ["lunch"], "minutes": 5},
        )
        saved = await ChallengeRecommendation.get(id=recommendation.id)
        assert saved.source_type == RecommendationSourceType.CONVERSATION
        assert saved.cycle_id == 1
        assert saved.conversation_snapshot == {"answers": ["lunch"]}
        assert saved.llm_model_version == "TEST-MODEL"
        assert saved.evidence_card_ids == ["TEST-CARD"]
        assert saved.proposed_goal == {"slots": ["lunch"], "minutes": 5}

    async def test_factor_enabled_index_exists_in_database(self) -> None:
        db = Challenge._meta.db
        if db.capabilities.dialect == "mysql":
            rows = await db.execute_query_dict("SHOW INDEX FROM challenges")
            indexes: dict[str, list[tuple[int, str]]] = {}
            for row in rows:
                indexes.setdefault(row["Key_name"], []).append((row["Seq_in_index"], row["Column_name"]))
            assert any(
                [column for _, column in sorted(columns)] == ["factor_key", "is_enabled"]
                for columns in indexes.values()
            )
        else:
            assert db.capabilities.dialect == "sqlite"
            rows = await db.execute_query_dict("PRAGMA index_list('challenges')")
            for row in rows:
                index_name = row["name"].replace("'", "''")
                columns = await db.execute_query_dict(f"PRAGMA index_info('{index_name}')")
                if [column["name"] for column in columns] == ["factor_key", "is_enabled"]:
                    return
            pytest.fail("challenges(factor_key, is_enabled) index is missing")
