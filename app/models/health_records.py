from enum import StrEnum

from tortoise import fields, models


class InputMode(StrEnum):
    SIMPLE = "simple"
    DETAIL = "detail"
    DAILY = "daily"


class HealthRecord(models.Model):
    """건강정보 기록. 테이블 명세서 health_records 26컬럼 기준이다.

    이 테이블은 C(최병주)만 쓴다. 입력할 때마다 새 행을 쌓고 덮어쓰지 않는다 (REQ-HLTH-004).
    """

    id = fields.BigIntField(primary_key=True)
    # Cross-part table IDs stay scalar here. The DB DDL owns the FK constraints.
    user_id = fields.BigIntField()
    recorded_at = fields.DatetimeField(description="입력 시점. 덮어쓰지 않고 누적")
    input_mode = fields.CharEnumField(enum_type=InputMode, default=InputMode.SIMPLE)

    weight_kg = fields.DecimalField(max_digits=4, decimal_places=1, null=True)
    waist_cm = fields.DecimalField(max_digits=4, decimal_places=1, null=True)
    bmi = fields.DecimalField(max_digits=4, decimal_places=1, null=True)

    smoking_current = fields.BooleanField(null=True)
    alcohol_frequency = fields.SmallIntField(null=True)
    alcohol_amount = fields.SmallIntField(null=True)
    walking_days = fields.SmallIntField(null=True, description="주당 0~7")
    walking_minutes = fields.SmallIntField(null=True)
    strength_days = fields.SmallIntField(null=True, description="주당 0~7")
    sitting_minutes = fields.SmallIntField(null=True)
    family_history_dm = fields.BooleanField(null=True)
    family_history_htn = fields.BooleanField(null=True)
    dining_out_freq = fields.SmallIntField(null=True, description="외식 빈도 1~7. 1 거의 매일 2회+, 7 거의 안 함")

    # 정밀 모드 실측값. 라벨 정의에 쓰여 모델 입력에서는 뺀다 (AGENTS.md 모델 절)
    sbp = fields.SmallIntField(null=True)
    dbp = fields.SmallIntField(null=True)
    fasting_glucose = fields.SmallIntField(null=True)
    hba1c = fields.DecimalField(max_digits=3, decimal_places=1, null=True)
    triglyceride = fields.SmallIntField(null=True)
    hdl = fields.SmallIntField(null=True)
    total_cholesterol = fields.SmallIntField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "health_records"
        indexes = (("user_id", "recorded_at"),)
