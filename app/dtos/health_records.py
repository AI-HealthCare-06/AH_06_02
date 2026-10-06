from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.dtos.base import BaseSerializerModel
from app.models.health_records import InputMode

# 범위 근거가 있는 필드는 app/core/validators/health_validators.py 에서 HLTH_VALUE_OUT_OF_RANGE 로 검사한다.
# 여기서는 형식과, 범위 근거가 없는 필드의 DB 타입 한계만 본다.
SmallInt = Annotated[int, Field(ge=-32768, le=32767)]
OneDecimal = Annotated[Decimal, Field(decimal_places=1)]
Decimal4_1 = Annotated[Decimal, Field(max_digits=4, decimal_places=1)]
Decimal3_1 = Annotated[Decimal, Field(max_digits=3, decimal_places=1)]


class _HealthRecordInput(BaseModel):
    # 모드별로 받는 필드가 다르다. 그 모드에 없는 필드가 오면 조용히 버리지 않고 400으로 돌려준다
    model_config = ConfigDict(extra="forbid")


class SimpleHealthRecordInput(_HealthRecordInput):
    """간편 모드. 최근 4주 기준 생활습관 (REQ-HLTH-001). 모두 선택 입력이다."""

    input_mode: Literal[InputMode.SIMPLE]
    weight_kg: OneDecimal | None = None
    waist_cm: Decimal4_1 | None = None
    smoking_current: bool | None = None
    alcohol_frequency: int | None = None
    alcohol_amount: int | None = None
    walking_days: int | None = None
    walking_minutes: int | None = None
    strength_days: int | None = None
    sitting_minutes: int | None = None
    family_history_dm: bool | None = None
    family_history_htn: bool | None = None
    dining_out_freq: int | None = None


class DetailHealthRecordInput(SimpleHealthRecordInput):
    """정밀 모드. 간편 항목에 실측 6항목을 더한다 (REQ-HLTH-002). total_cholesterol은 받지 않는다."""

    input_mode: Literal[InputMode.DETAIL]  # type: ignore[assignment]
    sbp: int | None = None
    dbp: SmallInt | None = None
    fasting_glucose: int | None = None
    hba1c: Decimal3_1 | None = None
    triglyceride: SmallInt | None = None
    hdl: SmallInt | None = None


class DailyHealthRecordInput(_HealthRecordInput):
    """일일 기록. 다섯 항목 모두 선택이지만 전부 비면 저장하지 않는다 (REQ-HLTH-006)."""

    input_mode: Literal[InputMode.DAILY]
    weight_kg: OneDecimal | None = None
    waist_cm: Decimal4_1 | None = None
    sbp: int | None = None
    dbp: SmallInt | None = None
    fasting_glucose: int | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "DailyHealthRecordInput":
        if all(value is None for key, value in self.model_dump().items() if key != "input_mode"):
            raise ValueError("일일 기록은 한 항목 이상 입력해주세요.")
        return self


HealthRecordCreateRequest = Annotated[
    SimpleHealthRecordInput | DetailHealthRecordInput | DailyHealthRecordInput,
    Field(discriminator="input_mode"),
]


class HealthRecordCreateResponse(BaseSerializerModel):
    """HLTH-01 응답."""

    health_record_id: int = Field(validation_alias="id")
    input_mode: InputMode
    recorded_at: datetime
    bmi: float | None


class HealthRecordItem(BaseSerializerModel):
    """HLTH-02 목록 한 행. 원본 기록을 그대로 보여준다."""

    health_record_id: int = Field(validation_alias="id")
    recorded_at: datetime
    input_mode: InputMode
    weight_kg: float | None
    waist_cm: float | None
    bmi: float | None
    sbp: int | None
    dbp: int | None
    fasting_glucose: int | None
    hba1c: float | None
    triglyceride: int | None
    hdl: int | None
    smoking_current: bool | None
    alcohol_frequency: int | None
    alcohol_amount: int | None
    walking_days: int | None
    walking_minutes: int | None
    strength_days: int | None
    sitting_minutes: int | None
    family_history_dm: bool | None
    family_history_htn: bool | None
    dining_out_freq: int | None
