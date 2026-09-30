from enum import StrEnum

from tortoise import fields, models


class DiseaseScope(StrEnum):
    COMMON = "common"
    DIABETES = "diabetes"
    HYPERTENSION = "hypertension"


class ImpactSource(StrEnum):
    CONTRIBUTION = "contribution"
    MEASURED = "measured"
    GLOBAL = "global"


class DefaultImpactSource(StrEnum):
    CONTRIBUTION = "contribution"
    MEASURED = "measured"


class MonsterState(StrEnum):
    RAGE = "rage"
    CAUTION = "caution"
    STABLE = "stable"
    NOT_CONTRIBUTING = "not_contributing"
    RESOLVED = "resolved"
    SEALED = "sealed"
    UNMEASURED = "unmeasured"


class ChallengeCategory(StrEnum):
    ACTIVITY = "activity"
    DIET = "diet"
    SMOKING = "smoking"
    ALCOHOL = "alcohol"
    BODY = "body"
    SLEEP = "sleep"


class GoalType(StrEnum):
    BOOLEAN = "boolean"
    COUNT = "count"
    DURATION = "duration"
    QUANTITY = "quantity"


class VerificationType(StrEnum):
    MANUAL = "manual"
    PHOTO = "photo"
    TIMER = "timer"
    VALUE = "value"
    TIME = "time"
    SYSTEM = "system"


class ChallengeDifficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    CHALLENGE = "challenge"


class RelationType(StrEnum):
    DIRECT = "direct"
    SUPPORTING = "supporting"
    GENERAL = "general"


class ContextType(StrEnum):
    NONE = "none"
    MEAL = "meal"
    EVENT = "event"


class UserChallengeStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class Monster(models.Model):
    id = fields.BigIntField(primary_key=True)
    code = fields.CharField(max_length=20, unique=True)
    no = fields.SmallIntField(unique=True)
    name = fields.CharField(max_length=30)
    title = fields.CharField(max_length=60, null=True)
    factor_keys = fields.JSONField()
    disease_scope = fields.CharEnumField(DiseaseScope, default=DiseaseScope.COMMON)
    default_impact_source = fields.CharEnumField(DefaultImpactSource, default=DefaultImpactSource.CONTRIBUTION)
    is_enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "monsters"


class UserMonster(models.Model):
    id = fields.BigIntField(primary_key=True)
    # Cross-part table IDs stay scalar here. The DB DDL owns the FK constraints,
    # and D does not import/write A/B/C models directly.
    user_id = fields.BigIntField()
    monster_id = fields.BigIntField()
    impact_score = fields.SmallIntField(null=True)
    state = fields.CharEnumField(MonsterState, default=MonsterState.UNMEASURED)
    sealed_at = fields.DatetimeField(null=True)
    resolved_at = fields.DatetimeField(null=True)
    reawakened_at = fields.DatetimeField(null=True)
    seal_count = fields.SmallIntField(default=0)
    impact_source = fields.CharEnumField(ImpactSource, default=ImpactSource.CONTRIBUTION)
    last_prediction_id = fields.BigIntField(null=True)
    last_health_record_id = fields.BigIntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    weekly_progress = fields.SmallIntField(default=0)
    progress_week_start = fields.DateField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_monsters"
        unique_together = (("user_id", "monster_id"),)


class Challenge(models.Model):
    id = fields.BigIntField(primary_key=True)
    code = fields.CharField(max_length=40, unique=True)
    title = fields.CharField(max_length=80)
    description = fields.CharField(max_length=255, null=True)
    category = fields.CharEnumField(ChallengeCategory)
    factor_key = fields.CharField(max_length=50, null=True)
    goal_type = fields.CharEnumField(GoalType)
    target_value = fields.DecimalField(max_digits=6, decimal_places=1, null=True)
    unit = fields.CharField(max_length=20, null=True)
    daily_target_count = fields.SmallIntField(default=1)
    duration_days = fields.SmallIntField(default=7)
    verification_type = fields.CharEnumField(VerificationType, default=VerificationType.TIMER)
    difficulty = fields.CharEnumField(ChallengeDifficulty, default=ChallengeDifficulty.EASY)
    relation_type = fields.CharEnumField(RelationType, default=RelationType.SUPPORTING)
    exclude_condition = fields.CharField(max_length=200, null=True)
    context_label = fields.CharField(max_length=40, null=True)
    manual_fallback_allowed = fields.BooleanField(default=True)
    context_type = fields.CharEnumField(ContextType, default=ContextType.NONE)
    context_slots = fields.JSONField(null=True)
    reward_xp = fields.SmallIntField(default=0)
    progress_value = fields.SmallIntField(default=10)
    is_enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "challenges"


class UserChallenge(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField()
    challenge_id = fields.BigIntField()
    recommendation_id = fields.BigIntField(null=True)
    source_prediction_id = fields.BigIntField(null=True)
    status = fields.CharEnumField(UserChallengeStatus, default=UserChallengeStatus.ACTIVE)
    start_date = fields.DateField()
    end_date = fields.DateField()
    daily_target_count_snapshot = fields.SmallIntField()
    target_value_snapshot = fields.DecimalField(max_digits=6, decimal_places=1, null=True)
    duration_days_snapshot = fields.SmallIntField()
    completed_at = fields.DatetimeField(null=True)
    stopped_at = fields.DatetimeField(null=True)
    stop_reason = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_challenges"
        indexes = (("user_id", "status"),)
