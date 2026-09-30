from app.models.challenges import (
    ChallengeLog,
    ChallengeRecommendation,
    CooldownChoice,
    RecommendationAction,
    Reward,
    UserReward,
    VerificationMethod,
)


def test_remaining_d_models_use_fixed_table_names() -> None:
    assert ChallengeRecommendation._meta.db_table == "challenge_recommendations"
    assert ChallengeLog._meta.db_table == "challenge_logs"
    assert Reward._meta.db_table == "rewards"
    assert UserReward._meta.db_table == "user_rewards"


def test_recommendation_action_contract() -> None:
    assert {item.value for item in RecommendationAction} == {
        "accepted",
        "rejected",
        "ignored",
        "not_applicable",
    }


def test_recommendation_cooldown_contract() -> None:
    assert {item.value for item in CooldownChoice} == {
        "7d",
        "30d",
        "until_manual",
    }


def test_challenge_log_verification_methods_include_fallback() -> None:
    assert {item.value for item in VerificationMethod} == {
        "manual",
        "photo",
        "timer",
        "value",
        "time",
        "system",
        "manual_fallback",
    }


def test_challenge_log_has_mvp_evidence_and_reward_fields() -> None:
    required = {
        "evidence_url",
        "verification_score",
        "reward_eligible",
        "xp_granted",
        "context_slot",
    }
    assert required.issubset(ChallengeLog._meta.fields_map)


def test_user_reward_is_unique_per_reward() -> None:
    assert ("user_id", "reward_id") in UserReward._meta.unique_together

def test_challenge_has_safety_check_flag() -> None:
    from app.models.challenges import Challenge

    assert "safety_check_required" in Challenge._meta.fields_map