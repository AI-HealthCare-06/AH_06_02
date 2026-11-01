"""질의 챗봇 선택 단계(판단 모델). AI 는 정해진 챌린지 중에서 순위만 매기고 챌린지·목표 값·문장을 만들지 않는다.

후보는 사용자가 선택형 질문에 '할 수 있어요'로 답한 챌린지뿐이다. 판단 모델은 후보마다 한 글자 라벨을 받아
가장 알맞은 라벨 하나에 대한 확률 분포(logprobs)만 돌려준다(DecisionRAG 의 Multiple-Choice 판단). 토큰으로
문장을 만들지 않으므로 이유·숫자를 지어낼 수 없다. 서버가 확률 순으로 최대 3개를 고르고, 이유 문장은
사용자가 고른 답의 질문 페이지 문장으로, 근거 카드는 그 챌린지의 승인 카드로 채운다.
목표량·횟수·시간대·난이도·단계는 규칙(proposed_goal: 지난 주기 수행률로 정한 단계, 없으면 마스터)이 정하고
서버가 그 값을 채워 서빙한다. 클라이언트는 서빙 JSON 의 recommendation_id 로 시작한다(CHLG-05).
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.models.challenges import Challenge
from app.services.challenge_goals import Goal
from app.services.rag_cards import SUPPORTED_CODES, EvidenceCard, SituationAnswers

MAX_SELECTIONS = 3
#: 후보에 붙이는 라벨. 1단계 지원 키가 21개라 한 글자로 모두 담긴다
LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#: 판단 모델 확률 중 후보 라벨에 실린 몫이 이보다 작으면 후보 밖을 고른 것으로 보고 버린다
MIN_LABEL_MASS = 0.5
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
FALLBACK_REASON = "답해 주신 내용에 맞춰 골랐어요."


@dataclass(frozen=True)
class ValidatedSelection:
    challenge: Challenge
    cards: list[EvidenceCard]
    reason: str
    #: 이유 문장이 검사를 못 넘어 고정 문장으로 바꿨는지
    reason_replaced: bool
    #: 판단 모델이 준 확률(후보 라벨끼리 합이 1). 후보가 하나라 모델을 부르지 않았으면 1
    probability: float


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


def candidate_labels(codes: set[str]) -> dict[str, str]:
    """라벨 → 챌린지 코드. 코드 순서로 붙여 같은 후보면 같은 라벨이다."""
    if not codes or len(codes) > len(LABELS):
        raise ValueError("라벨을 붙일 수 있는 후보 수가 아닙니다.")
    return dict(zip(LABELS, sorted(codes), strict=False))


def validate_judgment(raw: object, labels: dict[str, str]) -> dict[str, float]:
    """판단 모델 출력(라벨 → 확률)을 코드 → 확률로 바꾼다. 후보 라벨끼리 합이 1이 되게 다시 나눈다.

    후보 라벨에 실린 확률이 MIN_LABEL_MASS 보다 작으면 모델이 후보 밖을 고른 것이라 ValueError 로 버린다.
    """
    if not isinstance(raw, dict):
        raise ValueError("판단 모델 출력은 라벨별 확률이어야 합니다.")
    probabilities: dict[str, float] = {}
    for label, value in raw.items():
        if label in labels and isinstance(value, int | float) and 0 <= value <= 1:
            probabilities[labels[label]] = probabilities.get(labels[label], 0.0) + float(value)
    mass = sum(probabilities.values())
    if mass < MIN_LABEL_MASS:
        raise ValueError("판단 모델이 후보 라벨을 고르지 않았습니다.")
    return {code: probabilities.get(code, 0.0) / mass for code in labels.values()}


def rank_selections(
    probabilities: dict[str, float],
    selectable: dict[str, Challenge],
    cards: list[EvidenceCard],
    answers: SituationAnswers,
    reasons: dict[str, str | None],
    allowed_numbers: dict[str, set[Decimal]],
) -> list[ValidatedSelection]:
    """확률 순(같으면 코드 순)으로 최대 3개. 이유 문장은 질문 페이지 문장, 근거는 그 챌린지의 첫 승인 카드다.

    cards 는 검색에 걸린 카드가 앞에 오도록 정렬돼 있어, 사용자 말과 겹친 카드가 먼저 붙는다.
    """
    result: list[ValidatedSelection] = []
    for code in sorted(selectable, key=lambda item: (-probabilities.get(item, 0.0), item))[:MAX_SELECTIONS]:
        if code not in SUPPORTED_CODES or not answers.supports(code):
            raise ValueError("1단계 21개 챌린지 중 사용자가 할 수 있다고 답한 코드가 아닙니다.")
        card = next((c for c in cards if c.challenge_code == code and c.status == "approved"), None)
        if card is None:
            continue
        reason = reasons.get(code)
        replaced = reason is None or not reason_is_safe(reason, allowed_numbers.get(code, set()))
        result.append(
            ValidatedSelection(
                challenge=selectable[code],
                cards=[card],
                reason=FALLBACK_REASON if replaced or reason is None else reason,
                reason_replaced=replaced,
                probability=probabilities.get(code, 0.0),
            )
        )
    return result
