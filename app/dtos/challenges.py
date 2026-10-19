from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.challenges import ContextSlot, VerificationMethod


class ChallengeStartRequest(BaseModel):
    recommendation_ids: list[int] = Field(min_length=1, max_length=3)
    safety_confirmed: bool | None = None
    scheduled_dates: list[date] | None = Field(default=None, min_length=1, max_length=28)

    @field_validator("scheduled_dates", mode="before")
    @classmethod
    def check_calendar_dates(cls, value: object) -> object:
        """예정일은 시각이나 숫자가 아닌 KST YYYY-MM-DD 날짜로 받는다."""
        if value is None:
            return value
        if not isinstance(value, list) or any(
            not isinstance(day, str) or len(day) != 10 or date.fromisoformat(day).isoformat() != day for day in value
        ):
            raise ValueError("예정 이용일은 YYYY-MM-DD 날짜 목록이어야 합니다.")
        return value


class ChallengeStopRequest(BaseModel):
    stop_reason: str | None = Field(default=None, max_length=100)


class AttackTargetRequest(BaseModel):
    user_monster_id: int = Field(gt=0, strict=True)


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
    timer_session_id: int | None = Field(default=None, gt=0, strict=True)
