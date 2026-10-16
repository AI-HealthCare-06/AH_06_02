"""저장한 위협도 설명의 구조. 현재 모델로 과거 설명을 재계산하지 않는다."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ImpactFactor(BaseModel):
    disease: Literal["diabetes", "hypertension"]
    factor_key: str = Field(min_length=1, max_length=50)
    score: int = Field(ge=0, le=100, strict=True)
    source: Literal["contribution", "global"]


class ImpactExplanationSnapshot(BaseModel):
    schema_version: Literal["v1"]
    policy_version: Literal["max-factor-v1"]
    model_version: str = Field(min_length=1, max_length=64)
    calculated_at: datetime
    health_record_id: int = Field(gt=0, strict=True)
    prediction_id: int | None
    contribution_prediction_id: int | None = None
    impact_score: int = Field(ge=0, le=100, strict=True)
    impact_source: Literal["contribution", "global"]
    candidates: list[ImpactFactor] = Field(min_length=1)
    winners: list[ImpactFactor] = Field(min_length=1)
