"""질의 챗봇 선택 단계(디시전 모델). AI 는 정해진 챌린지 코드 중에서 고르기만 하고 챌린지·목표 값을 만들지 않는다.

출력은 JSON 스키마로 제한한다. challenge_code 와 그 코드의 evidence_card_ids 는 이번 요청에서 고를 수 있는 값만
enum 으로 넣어 그 밖의 값은 토큰으로 나올 수 없게 하고(Structured Outputs strict), 서버가 다시 검사한다.
목표량·횟수·시간대·난이도·단계는 규칙(proposed_goal: 지난 주기 수행률로 정한 단계, 없으면 마스터)이 정하고
서버가 그 값을 채워 서빙한다. 클라이언트는 서빙 JSON 의 recommendation_id 로 시작한다(CHLG-05).
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.challenges import Challenge
from app.services.challenge_goals import Goal
from app.services.rag_cards import SUPPORTED_CODES, EvidenceCard, SituationAnswers

MAX_SELECTIONS = 3
MAX_REASON_LENGTH = 200
MAX_REPLY_LENGTH = 600

#: 질환 치료·예방·수치 개선을 단정하거나 위험도·진단을 말하는 표현 (계약 3절 "서버가 거절하는 응답")
CLAIM_PATTERN = re.compile(
    r"치료|완치|낫(?:는|게|습|아)|예방|막(?:아|을|는)|줄(?:여|일|어)|낮(?:춰|출|아|추)|감소|개선|효과|보장|"
    r"반드시|확실|틀림없|진단|당뇨|고혈압|혈압|혈당|위험도|위협도|질환|질병|%|퍼센트"
)
DIGIT_PATTERN = re.compile(r"\d")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
#: 근거 카드 guidance 의 운영 기준 말투. 사용자에게 건네는 이유 문장으로는 쓰지 않는다
OPERATOR_PATTERN = re.compile(r"답한 경우|답하면|제안한다|제안하지|않는다\.?$|원형|운영 기준")
#: 이유 문장이 검사를 못 넘으면 쓰는 고정 문장. 카드 원문은 운영자용이라 쓰지 않는다
FALLBACK_REASON = "대화 내용에 맞춰 골랐어요."


class ChatSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_code: str
    evidence_card_ids: list[str] = Field(min_length=1, max_length=3)
    reason: str = Field(max_length=MAX_REASON_LENGTH)


class ChatDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[ChatSelection] = Field(max_length=MAX_SELECTIONS)


def decision_schema(cards_by_code: dict[str, list[str]]) -> dict[str, Any]:
    """Structured Outputs(strict) 스키마. 코드마다 한 갈래(anyOf)를 두고 그 코드의 카드 ID 만 enum 으로 허용한다.

    코드 목록과 카드 목록을 따로 enum 으로 두면 다른 챌린지의 카드를 붙일 수 있어 갈래로 묶는다.
    """
    branches = [
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["challenge_code", "evidence_card_ids", "reason"],
            "properties": {
                "challenge_code": {"type": "string", "enum": [code]},
                "evidence_card_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {"type": "string", "enum": sorted(card_ids)},
                },
                "reason": {"type": "string"},
            },
        }
        for code, card_ids in sorted(cards_by_code.items())
        if card_ids
    ]
    if not branches:
        raise ValueError("고를 수 있는 챌린지와 근거 카드가 있어야 합니다.")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["selections"],
        "properties": {
            "selections": {"type": "array", "maxItems": MAX_SELECTIONS, "items": {"anyOf": branches}},
        },
    }


@dataclass(frozen=True)
class ValidatedSelection:
    challenge: Challenge
    cards: list[EvidenceCard]
    reason: str
    #: 이유 문장이 검사를 못 넘어 고정 문장으로 바꿨는지
    reason_replaced: bool


def has_unsafe_claim(text: str, *, allow_numbers: bool) -> bool:
    if CLAIM_PATTERN.search(text):
        return True
    return not allow_numbers and bool(DIGIT_PATTERN.search(text))


def goal_numbers(goal: Goal) -> set[Decimal]:
    """이유 문장에 써도 되는 숫자. 서빙하는 목표량과 하루 횟수뿐이다."""
    numbers = {Decimal(goal.daily_target_count).normalize()}
    if goal.target_value is not None:
        numbers.add(Decimal(goal.target_value).normalize())
    return numbers


def reason_is_safe(reason: str, allowed_numbers: set[Decimal]) -> bool:
    """단정 표현·운영자 말투가 없고, 숫자는 서빙하는 목표 값과 같은 것만 있는 이유 문장."""
    if not reason or CLAIM_PATTERN.search(reason) or OPERATOR_PATTERN.search(reason):
        return False
    return all(Decimal(number).normalize() in allowed_numbers for number in NUMBER_PATTERN.findall(reason))


def validate_selections(
    output: object,
    selectable: dict[str, Challenge],
    sent_cards: list[EvidenceCard],
    answers: SituationAnswers,
    allowed_numbers: dict[str, set[Decimal]],
) -> list[ValidatedSelection]:
    """스키마 검증 + 코드·카드 유효성 검증. 하나라도 어긋나면 ValueError 로 전체를 버리고 규칙 추천으로 돌아간다.

    목표 값 키(target_value 등)가 섞인 출력은 스키마(extra=forbid)에서 거절된다.
    이유 문장만 어긋나면 선택은 살리고 문장을 FALLBACK_REASON 으로 바꾼다.
    """
    parsed = ChatDecision.model_validate(output)
    cards = {card.card_id: card for card in sent_cards if card.status == "approved"}
    seen: set[str] = set()
    result: list[ValidatedSelection] = []
    for item in parsed.selections:
        code = item.challenge_code
        if code not in SUPPORTED_CODES or code not in selectable or code in seen or not answers.supports(code):
            raise ValueError("1단계 21개 챌린지 중 지금 고를 수 있는 코드가 아닙니다.")
        seen.add(code)
        evidence = [cards.get(card_id) for card_id in item.evidence_card_ids]
        if len(set(item.evidence_card_ids)) != len(item.evidence_card_ids) or any(
            card is None or card.challenge_code != code for card in evidence
        ):
            raise ValueError("보낸 승인 카드가 아니거나 다른 챌린지의 카드입니다.")
        approved = [card for card in evidence if card is not None]
        reason = item.reason.strip()
        replaced = not reason_is_safe(reason, allowed_numbers.get(code, set()))
        result.append(
            ValidatedSelection(
                challenge=selectable[code],
                cards=approved,
                reason=FALLBACK_REASON if replaced else reason,
                reason_replaced=replaced,
            )
        )
    return result
