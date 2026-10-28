from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.challenges import ContextSlot, VerificationMethod
from app.services.rag_cards import SituationAnswers


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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=400)


#: 대화 길이 상한. 클라이언트가 대화를 들고 있고 서버는 저장하지 않는다
MAX_CHAT_MESSAGES = 12


class ChallengeChatRequest(BaseModel):
    """질의 챗봇 1단계(대화). 마지막 메시지는 사용자 질문이다."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_CHAT_MESSAGES)

    @field_validator("messages")
    @classmethod
    def ends_with_user(cls, messages: list[ChatMessage]) -> list[ChatMessage]:
        if messages[-1].role != "user":
            raise ValueError("마지막 메시지는 사용자 질문이어야 합니다.")
        return messages


class ChallengeSelectRequest(BaseModel):
    """질의 챗봇 2단계(선택). messages 는 1단계 대화, answers 는 선택형 질문의 답, asked 는 이미 물은 질문 키다."""

    messages: list[ChatMessage] = Field(default_factory=list, max_length=MAX_CHAT_MESSAGES)
    answers: SituationAnswers = Field(default_factory=SituationAnswers)
    asked: list[str] = Field(default_factory=list, max_length=3)
