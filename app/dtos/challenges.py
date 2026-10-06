from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.challenges import ContextSlot, VerificationMethod


class ChallengeStartRequest(BaseModel):
    recommendation_ids: list[int] = Field(min_length=1, max_length=3)
    safety_confirmed: bool | None = None


class ChallengeStopRequest(BaseModel):
    stop_reason: str | None = Field(default=None, max_length=100)


class RecommendationActionRequest(BaseModel):
    """CHLG-03. cooldown_choice 는 서비스에서 검사해 CHLG_INVALID_COOLDOWN 으로 돌려준다."""

    action: Literal["rejected", "not_applicable"]
    cooldown_choice: str | None = None


class ChallengeLogRequest(BaseModel):
    """CHLG-07."""

    occurred_at: datetime
    context_slot: ContextSlot | None = None
    value: Annotated[Decimal, Field(max_digits=6, decimal_places=1)] | None = None
    verification_method: VerificationMethod
    evidence_url: str | None = Field(default=None, max_length=255)
