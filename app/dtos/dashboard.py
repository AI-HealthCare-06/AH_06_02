from datetime import datetime

from pydantic import BaseModel

from app.dtos.base import BaseSerializerModel
from app.models.predictions import Disease, RiskGrade


class RiskSummary(BaseModel):
    """DASH-01 질환별 최신 위험도."""

    disease: Disease
    probability: float
    # 등급 경계값이 정해지기 전까지 키는 두고 값은 항상 null 이다 (REQ-PRED-004)
    grade: RiskGrade | None = None
    # 직전 done 예측 대비 percentage points. 직전이 없으면 null
    delta: float | None
    predicted_at: datetime | None


class LatestHealthRecord(BaseModel):
    health_record_id: int
    recorded_at: datetime


class DashboardSummaryResponse(BaseModel):
    prediction_available: bool
    risks: list[RiskSummary]
    latest_health_record: LatestHealthRecord | None


class TrendMeasurements(BaseSerializerModel):
    weight_kg: float | None
    waist_cm: float | None
    sbp: int | None
    dbp: int | None
    fasting_glucose: int | None
    hba1c: float | None


class TrendRisk(BaseModel):
    disease: Disease
    probability: float
    predicted_at: datetime | None


class TrendPoint(BaseModel):
    recorded_at: datetime
    health_record_id: int
    measurements: TrendMeasurements
    risks: list[TrendRisk]


class DashboardTrendsResponse(BaseModel):
    points: list[TrendPoint]
