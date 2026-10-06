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


class ContextSlot(StrEnum):
    LUNCH = "lunch"
    DINNER = "dinner"


class UserChallengeStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    # D28 경계에서 끝난 레거시 상태명. 화면에는 "기간 종료"로 표시하고 습관 졸업을 뜻하지 않는다
    GRADUATED = "graduated"
    ABANDONED = "abandoned"


class AttackCycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class OccurrenceStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    MISSED = "missed"


class Monster(models.Model):
    id = fields.BigIntField(primary_key=True)
    code = fields.CharField(max_length=20, unique=True)
    no = fields.SmallIntField(unique=True)
    name = fields.CharField(max_length=30)
    title = fields.CharField(max_length=60, null=True)
    factor_keys: list[str] = fields.JSONField()
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
    context_slots: list[str] | None = fields.JSONField(null=True)
    reward_xp = fields.SmallIntField(default=0)
    progress_value = fields.SmallIntField(default=10)
    is_enabled = fields.BooleanField(default=True)
    safety_check_required = fields.BooleanField(default=False)
    context_priority = fields.SmallIntField(null=True, description="같은 factor 안의 후보 순위")
    personalization_policy: dict[str, object] | None = fields.JSONField(
        null=True, description="NULL이면 기존 고정 원형"
    )
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
    cycle_id = fields.BigIntField(null=True, db_index=True, description="레거시·주기 밖 미션만 NULL")
    status = fields.CharEnumField(UserChallengeStatus, default=UserChallengeStatus.ACTIVE)
    start_date = fields.DateField()
    end_date = fields.DateField()
    daily_target_count_snapshot = fields.SmallIntField()
    target_value_snapshot = fields.DecimalField(max_digits=6, decimal_places=1, null=True)
    duration_days_snapshot = fields.SmallIntField()
    completed_at = fields.DatetimeField(null=True)
    stopped_at = fields.DatetimeField(null=True)
    stop_reason = fields.CharField(max_length=100, null=True)
    habit_established = fields.BooleanField(null=True, default=None, description="1단계는 판정 유예. NULL=미평가")
    goal_config_snapshot: dict[str, object] | None = fields.JSONField(
        null=True, description="예정 기회 배열은 담지 않는다"
    )
    completed_occurrence_count = fields.SmallIntField(null=True, description="종료 시점 인정 완료 기회 수")
    planned_occurrence_count = fields.SmallIntField(null=True, description="종료 시점 예정 기회 수. 수행률 분모")
    completion_rate = fields.DecimalField(max_digits=5, decimal_places=4, null=True, description="분모 0이면 NULL")
    summary_computed_at = fields.DatetimeField(null=True)
    summary_policy_version = fields.CharField(max_length=20, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_challenges"
        indexes = (("user_id", "status"),)


class UserAttackCycle(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField()
    # 같은 사용자 소유인지는 DDL의 복합 FK (target_user_monster_id, user_id)가 강제한다.
    # active_user_id 생성 컬럼과 그 유니크도 Tortoise가 만들지 못해 migration에서 raw SQL로 건다.
    target_user_monster_id = fields.BigIntField(description="같은 사용자 소유의 공략 대상")
    start_date = fields.DateField(null=True, description="draft에서는 NULL. KST D0")
    end_date = fields.DateField(null=True, description="start_date+27. 마지막 수행 가능 날짜 포함")
    status = fields.CharEnumField(AttackCycleStatus, default=AttackCycleStatus.DRAFT)
    extra_added_count = fields.SmallIntField(default=0, description="2주차 이후 추가 횟수 0 또는 1")
    policy_version = fields.CharField(max_length=32)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_attack_cycles"
        indexes = (("user_id", "status"),)


class UserChallengeOccurrence(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_challenge_id = fields.BigIntField()
    scheduled_date = fields.DateField(db_index=True, description="KST 달력 날짜")
    slot_code = fields.CharField(
        max_length=20,
        default="",
        description="lunch·dinner 등. 독립 회차는 빈 문자열. NULL은 유니크가 걸리지 않아 쓰지 않는다",
    )
    sequence_no = fields.SmallIntField(default=1, description="같은 날 독립 회차 번호")
    status = fields.CharEnumField(
        OccurrenceStatus,
        default=OccurrenceStatus.PLANNED,
        description="completed만 수행률 분자. skipped·missed는 분모에만 남는다",
    )
    completed_log_id = fields.BigIntField(null=True, unique=True, description="이 기회를 인정한 수행 기록")
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_challenge_occurrences"
        unique_together = (("user_challenge_id", "scheduled_date", "slot_code", "sequence_no"),)
        indexes = (("user_challenge_id", "status"),)


# ---- D persistence models: recommendation / logs / rewards ----


class RecommendationSourceType(StrEnum):
    PREDICTION_PERSONAL = "prediction_personal"
    DIAGNOSIS_GLOBAL = "diagnosis_global"
    CONVERSATION = "conversation"


class RecommendationAction(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IGNORED = "ignored"
    NOT_APPLICABLE = "not_applicable"


class CooldownChoice(StrEnum):
    DAYS_7 = "7d"
    DAYS_30 = "30d"
    UNTIL_MANUAL = "until_manual"


class ChallengeLogResult(StrEnum):
    DONE = "done"
    SKIPPED = "skipped"


class VerificationMethod(StrEnum):
    MANUAL = "manual"
    PHOTO = "photo"
    TIMER = "timer"
    VALUE = "value"
    TIME = "time"
    SYSTEM = "system"
    MANUAL_FALLBACK = "manual_fallback"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"
    SELF_CONFIRMED = "self_confirmed"


class RewardMotivationType(StrEnum):
    COLLECT = "collect"
    GROW = "grow"
    DECORATE = "decorate"


class RewardKind(StrEnum):
    ITEM = "item"
    BADGE = "badge"
    THEME = "theme"
    CARD = "card"


class ChallengeRecommendation(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField()
    challenge_id = fields.BigIntField()
    cycle_id = fields.BigIntField(null=True, description="추천을 만든 주기. 지난 주기 추천으로 시작 금지")
    source_type = fields.CharEnumField(RecommendationSourceType)
    factor_key = fields.CharField(max_length=50)
    factor_score = fields.DecimalField(max_digits=8, decimal_places=5, null=True)
    rank = fields.SmallIntField()
    recommended_at = fields.DatetimeField()
    action = fields.CharEnumField(RecommendationAction, null=True)
    acted_at = fields.DatetimeField(null=True)
    consecutive_reject_count = fields.SmallIntField(default=0)
    cooldown_choice = fields.CharEnumField(CooldownChoice, null=True)
    exclude_until = fields.DatetimeField(null=True)
    suppressed_until_manual = fields.BooleanField(default=False)
    conversation_snapshot: dict[str, object] | None = fields.JSONField(null=True, description="개인정보는 담지 않는다")
    llm_model_version = fields.CharField(max_length=32, null=True)
    evidence_card_ids: list[str] | None = fields.JSONField(null=True, description="승인 근거 카드 ID 배열")
    proposed_goal: dict[str, object] | None = fields.JSONField(null=True, description="서버 검증을 통과한 개인 목표")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "challenge_recommendations"
        indexes = (("user_id", "recommended_at"),)


class ChallengeLog(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_challenge_id = fields.BigIntField()
    log_date = fields.DateField()
    occurred_at = fields.DatetimeField()
    sequence_no = fields.SmallIntField(default=1)
    context_slot = fields.CharEnumField(ContextSlot, null=True)
    value = fields.DecimalField(max_digits=6, decimal_places=1, null=True)
    unit = fields.CharField(max_length=20, null=True)
    result = fields.CharEnumField(ChallengeLogResult, default=ChallengeLogResult.DONE)
    verification_method = fields.CharEnumField(VerificationMethod, default=VerificationMethod.TIMER)
    verification_status = fields.CharEnumField(
        VerificationStatus,
        default=VerificationStatus.SELF_CONFIRMED,
    )
    evidence_url = fields.CharField(max_length=255, null=True)
    verification_score = fields.DecimalField(max_digits=4, decimal_places=3, null=True)
    fallback_reason = fields.CharField(max_length=100, null=True)
    reward_eligible = fields.BooleanField(default=True)
    xp_granted = fields.SmallIntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "challenge_logs"
        unique_together = (("user_challenge_id", "log_date", "context_slot"),)
        indexes = (("user_challenge_id", "log_date"),)


class Reward(models.Model):
    id = fields.BigIntField(primary_key=True)
    code = fields.CharField(max_length=40, unique=True)
    name = fields.CharField(max_length=60)
    motivation_type = fields.CharEnumField(RewardMotivationType)
    reward_kind = fields.CharEnumField(RewardKind)
    unlock_condition = fields.CharField(max_length=120)
    required_level = fields.SmallIntField(null=True)
    linked_challenge_code = fields.CharField(max_length=40, null=True)
    is_enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "rewards"


class UserReward(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField()
    reward_id = fields.BigIntField()
    item_level = fields.SmallIntField(default=1)
    acquired_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_rewards"
        unique_together = (("user_id", "reward_id"),)
