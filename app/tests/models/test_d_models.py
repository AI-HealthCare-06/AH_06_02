from app.models.challenges import Challenge, Monster, MonsterState, UserChallenge, UserMonster


def test_d_models_use_fixed_table_names() -> None:
    assert Monster._meta.db_table == "monsters"
    assert UserMonster._meta.db_table == "user_monsters"
    assert Challenge._meta.db_table == "challenges"
    assert UserChallenge._meta.db_table == "user_challenges"


def test_user_monster_state_contract_has_seven_values() -> None:
    assert {state.value for state in MonsterState} == {
        "rage",
        "caution",
        "stable",
        "not_contributing",
        "resolved",
        "sealed",
        "unmeasured",
    }


def test_user_monster_has_resolved_at_and_weekly_progress() -> None:
    assert "resolved_at" in UserMonster._meta.fields_map
    assert "weekly_progress" in UserMonster._meta.fields_map
    assert "progress_week_start" in UserMonster._meta.fields_map


def test_challenge_has_mvp_verification_and_progress_fields() -> None:
    required = {
        "verification_type",
        "manual_fallback_allowed",
        "progress_value",
        "factor_key",
        "daily_target_count",
    }
    assert required.issubset(Challenge._meta.fields_map)
