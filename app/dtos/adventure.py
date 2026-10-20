"""v5 추가 API 요청. 알 수 없는 필드는 받아들이지 않는다."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.challenges import ContextSlot


class AdventureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimerStartRequest(AdventureRequest):
    context_slot: ContextSlot | None = None


class RewardClaimRequest(AdventureRequest):
    positions: list[Annotated[int, Field(strict=True, ge=0, le=4)]] = Field(min_length=3, max_length=3)


class AdventurerUpdateRequest(AdventureRequest):
    equipment: dict[str, str | None] = Field(default_factory=dict, max_length=4)
    room: dict[str, str | None] = Field(default_factory=dict, max_length=6)
