from pydantic import BaseModel, Field


class ChallengeStartRequest(BaseModel):
    recommendation_ids: list[int] = Field(min_length=1, max_length=3)
    safety_confirmed: bool | None = None


class ChallengeStopRequest(BaseModel):
    stop_reason: str | None = Field(default=None, max_length=100)
