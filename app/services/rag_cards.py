"""승인 근거 검색과 고정 원형 추천 검증. 정책·목표·보상은 생성하지 않는다."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: 1단계 추천 대상 7개 전부. 한 주기는 캐릭터 하나만 공략하므로 한 묶음에 활동형과 음주·흡연이 섞이지 않는다
SUPPORTED_CODES = frozenset(
    {
        "CH_WALK_AFTER_MEAL",
        "CH_WALK_ONE_STOP",
        "CH_STAND_HOURLY",
        "CH_STAIRS",
        "CH_STRENGTH_10",
        "CH_NO_DRINK_TODAY",
        "CH_NO_SMOKE_TODAY",
        "CH_WALK_EVENING_20",
        "CH_HOUSEWORK_15",
        "CH_SQUAT_15",
        "CH_WALL_PUSHUP_10",
        "CH_STAND_CALL",
        "CH_SCREEN_BREAK",
        "CH_WATER_NOT_SWEET",
        "CH_NO_LATE_SNACK",
        "CH_NO_ALCOHOL_AT_HOME",
        "CH_ALCOHOL_FREE_DRINK",
        "CH_POSTPONE_DRINKS",
        "CH_DELAY_FIRST_CIG",
        "CH_SMOKE_FREE_HOME",
        "CH_QUIT_REASON",
    }
)
ANSWER_FIELDS = {
    "CH_WALK_AFTER_MEAL": "meal_walk",
    "CH_WALK_ONE_STOP": "transit",
    "CH_STAND_HOURLY": "movement_breaks",
    "CH_STAIRS": "stairs",
    "CH_STRENGTH_10": "strength",
    "CH_NO_DRINK_TODAY": "no_drink",
    "CH_NO_SMOKE_TODAY": "no_smoke",
    "CH_WALK_EVENING_20": "evening_walk",
    "CH_HOUSEWORK_15": "housework",
    "CH_SQUAT_15": "squat",
    "CH_WALL_PUSHUP_10": "wall_pushup",
    "CH_STAND_CALL": "stand_call",
    "CH_SCREEN_BREAK": "screen_break",
    "CH_WATER_NOT_SWEET": "sweet_drink",
    "CH_NO_LATE_SNACK": "late_snack",
    "CH_NO_ALCOHOL_AT_HOME": "home_alcohol",
    "CH_ALCOHOL_FREE_DRINK": "alcohol_free",
    "CH_POSTPONE_DRINKS": "postpone_drinks",
    "CH_DELAY_FIRST_CIG": "first_cig",
    "CH_SMOKE_FREE_HOME": "smoke_free_home",
    "CH_QUIT_REASON": "quit_reason",
}
#: 답 키 → 챌린지 코드. 질문 페이지가 어느 챌린지 가지에 붙는지 정한다
CODE_BY_ANSWER_KEY = {field: code for code, field in ANSWER_FIELDS.items()}
#: 질문 페이지 원본. 질문 문장·선택지·이유 문장은 코드가 아니라 이 파일에 둔다
QUESTION_CORPUS = Path(__file__).resolve().parents[2] / "docs/01_planning/chatbot/questions-20261101.json"
#: "예"라고 답하면 후보로 남는 질문. 식후 걷기·한 정거장·움직임 휴식은 답 종류가 달라 따로 본다
YES_ANSWER_CODES = {
    code: field
    for code, field in ANSWER_FIELDS.items()
    if code not in {"CH_WALK_AFTER_MEAL", "CH_WALK_ONE_STOP", "CH_STAND_HOURLY"}
}


def classify_activity_range(answers: dict[str, str]) -> int | None:
    """확인된 선택지에서 운동 가능 범위를 산정한다."""
    if answers.get("light") == "yes" and answers.get("walk") == "yes" and answers.get("vigorous") == "yes":
        return 3
    if answers.get("light") == "yes" and answers.get("walk") == "yes" and answers.get("vigorous") == "no":
        return 2
    if answers.get("light") == "yes" and answers.get("walk") == "no" and answers.get("vigorous") in {"no", "unknown"}:
        return 1
    return None


def activity_question_budget(answers: dict[str, str]) -> int:
    """판정이 모호하면 확인 질문을 두 개까지 더 허용한다."""
    return 3 if classify_activity_range(answers) is not None else 5


def activity_range_allows(code: str, level: int | None) -> bool:
    """확인된 운동 범위에서 허용되는 챌린지인지 판정한다."""
    minimum = {
        "CH_STAND_HOURLY": 1,
        "CH_HOUSEWORK_15": 1,
        "CH_SQUAT_15": 1,
        "CH_STAND_CALL": 1,
        "CH_SCREEN_BREAK": 1,
        "CH_WALK_AFTER_MEAL": 2,
        "CH_WALK_ONE_STOP": 2,
        "CH_WALK_EVENING_20": 2,
        "CH_STAIRS": 3,
        "CH_STRENGTH_10": 3,
        "CH_WALL_PUSHUP_10": 3,
    }
    if code not in SUPPORTED_CODES:
        return False
    if code not in minimum:
        return True
    return level in {1, 2, 3} and level >= minimum[code]


class ActivityAnswers(BaseModel):
    """운동 가능 범위 질문에 누른 선택지 값."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    light: Literal["yes", "no", "unknown", "unsure", "limited"] = "unknown"
    walk: Literal["yes", "no", "unknown", "unsure", "limited"] = "unknown"
    vigorous: Literal["yes", "no", "unknown", "unsure", "limited"] = "unknown"
    clarifications: int = Field(default=0, ge=0, le=2, strict=True)


class SituationAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meal_walk: Literal["both", "both_indoor", "lunch_only", "dinner_only", "none", "unknown", "limited"] = "unknown"
    transit: Literal["yes", "no", "unknown", "limited"] = "unknown"
    movement_breaks: Literal["three", "less", "none", "unknown", "limited"] = "unknown"
    stairs: Literal["yes", "no", "unknown", "limited"] = "unknown"
    strength: Literal["yes", "no", "unknown", "limited"] = "unknown"
    evening_walk: Literal["yes", "no", "unknown", "limited"] = "unknown"
    housework: Literal["yes", "no", "unknown", "limited"] = "unknown"
    squat: Literal["yes", "no", "unknown", "limited"] = "unknown"
    wall_pushup: Literal["yes", "no", "unknown", "limited"] = "unknown"
    stand_call: Literal["yes", "no", "unknown", "limited"] = "unknown"
    screen_break: Literal["yes", "no", "unknown", "limited"] = "unknown"
    # 식습관·음주·흡연은 몸을 쓰는 활동이 아니라 "활동 제한" 선택지가 없다
    sweet_drink: Literal["yes", "no", "unknown"] = "unknown"
    late_snack: Literal["yes", "no", "unknown"] = "unknown"
    no_drink: Literal["yes", "no", "unknown"] = "unknown"
    home_alcohol: Literal["yes", "no", "unknown"] = "unknown"
    alcohol_free: Literal["yes", "no", "unknown"] = "unknown"
    postpone_drinks: Literal["yes", "no", "unknown"] = "unknown"
    no_smoke: Literal["yes", "no", "unknown"] = "unknown"
    first_cig: Literal["yes", "no", "unknown"] = "unknown"
    smoke_free_home: Literal["yes", "no", "unknown"] = "unknown"
    quit_reason: Literal["yes", "no", "unknown"] = "unknown"

    @property
    def activity_limited(self) -> bool:
        return "limited" in self.model_dump().values()

    def supports(self, code: str) -> bool:
        if self.activity_limited:
            return False
        if code in YES_ANSWER_CODES:
            return getattr(self, YES_ANSWER_CODES[code]) == "yes"
        return {
            "CH_WALK_AFTER_MEAL": self.meal_walk in {"both", "both_indoor"},
            "CH_WALK_ONE_STOP": self.transit == "yes",
            "CH_STAND_HOURLY": self.movement_breaks == "three",
        }.get(code, False)


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: str = Field(min_length=1, max_length=20)
    label: str = Field(min_length=1, max_length=40)
    #: 이 답으로 챌린지가 남을 때 보여 줄 이유 문장. 챌린지를 남기는 답에만 두고, 서버는 문장을 만들지 않는다
    reason: str | None = Field(default=None, min_length=1, max_length=200)


class QuestionPage(BaseModel):
    """선택형 질문 한 장. 같은 답 키에 표현이 다른 페이지를 여러 장 두고 그중 하나를 고른다."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    question_id: str = Field(min_length=1, max_length=40)
    answer_key: str
    text: str = Field(min_length=1, max_length=120)
    options: list[QuestionOption] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def check_options(self) -> QuestionPage:
        if self.answer_key not in CODE_BY_ANSWER_KEY:
            raise ValueError(f"{self.question_id}: 알 수 없는 답 키입니다.")
        allowed = set(get_args(SituationAnswers.model_fields[self.answer_key].annotation)) - {"unknown"}
        values = [option.value for option in self.options]
        if len(set(values)) != len(values) or not set(values) <= allowed:
            raise ValueError(f"{self.question_id}: 선택지 값이 답 키의 값과 맞지 않습니다.")
        # 몸을 쓰는 질문은 '몸 상태 때문에 어려워요'를 늘 함께 보여 보류로 이어지게 한다
        if "limited" in allowed and "limited" not in values:
            raise ValueError(f"{self.question_id}: 몸을 쓰는 질문에는 활동 제한 선택지가 있어야 합니다.")
        code = CODE_BY_ANSWER_KEY[self.answer_key]
        for option in self.options:
            keeps = SituationAnswers.model_validate({self.answer_key: option.value}).supports(code)
            if keeps != (option.reason is not None):
                raise ValueError(f"{self.question_id}: 챌린지를 남기는 답에만 이유 문장을 둡니다.")
        if not any(option.reason for option in self.options):
            raise ValueError(f"{self.question_id}: 챌린지를 남기는 답이 하나는 있어야 합니다.")
        return self

    def reason_for(self, value: str) -> str | None:
        return next((option.reason for option in self.options if option.value == value), None)


def load_questions(path: Path) -> list[QuestionPage]:
    pages = [QuestionPage.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
    if len({page.question_id for page in pages}) != len(pages):
        raise ValueError("질문 페이지 ID가 중복되었습니다.")
    if {page.answer_key for page in pages} != set(CODE_BY_ANSWER_KEY):
        raise ValueError("답 키마다 질문 페이지가 한 장 이상 있어야 합니다.")
    # 같은 답에는 어느 표현으로 물었든 같은 이유 문장을 보여 준다
    reasons: dict[tuple[str, str], str | None] = {}
    for page in pages:
        for option in page.options:
            if reasons.setdefault((page.answer_key, option.value), option.reason) != option.reason:
                raise ValueError(f"{page.question_id}: 같은 답의 이유 문장이 페이지마다 다릅니다.")
    return pages


@cache
def question_bank() -> tuple[QuestionPage, ...]:
    return tuple(load_questions(QUESTION_CORPUS))


class EvidenceCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    card_id: str = Field(min_length=1, max_length=32)
    version: str = Field(min_length=1, max_length=32)
    status: Literal["draft", "approved", "inactive"]
    challenge_code: str = Field(min_length=1, max_length=50)
    tags: list[str] = Field(min_length=1, max_length=12)
    guidance: str = Field(min_length=1, max_length=500)
    source_url: str
    source_section: str = Field(min_length=1)
    reviewed_at: str
    approved_by: str | None = None
    policy_note: str = "외부 근거는 일반 행동 방향이며 앱 목표량·난이도·효과 보장을 검증하지 않는다."

    @model_validator(mode="after")
    def check_approval(self) -> EvidenceCard:
        if not self.source_url.startswith("https://www.who.int/"):
            raise ValueError("첫 코퍼스는 확인한 WHO 공식 출처만 허용합니다.")
        if self.challenge_code not in SUPPORTED_CODES:
            raise ValueError("이번 코퍼스의 지원 키가 아닙니다.")
        if self.status == "approved" and not (self.approved_by or "").strip():
            raise ValueError("운영 승인자 기록이 필요합니다.")
        return self


def load_cards(path: Path) -> list[EvidenceCard]:
    cards = [EvidenceCard.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
    if len({card.card_id for card in cards}) != len(cards):
        raise ValueError("근거 카드 ID가 중복되었습니다.")
    return cards


def questions_for(codes: set[str], answers: SituationAnswers, asked: list[str]) -> list[dict[str, str]]:
    """대화형 추천(ConversationRecommendationService)의 질문. 답 키마다 첫 질문 페이지를 정해진 순서로 쓴다.

    질의 챗봇은 PageIndex.next_question 으로 질문 페이지를 랜덤으로 고른다.
    """
    first: dict[str, QuestionPage] = {}
    for page in question_bank():
        first.setdefault(page.answer_key, page)
    if len(asked) > 3 or len(set(asked)) != len(asked) or any(key not in first for key in asked):
        raise ValueError("질문 기록은 알려진 질문을 중복 없이 최대 세 개까지 사용합니다.")
    if answers.activity_limited:
        return []
    values = answers.model_dump()
    wanted = {ANSWER_FIELDS[code] for code in codes & SUPPORTED_CODES}
    keys = [key for key in ANSWER_FIELDS.values() if key in wanted and values[key] == "unknown" and key not in asked]
    return [{"key": key, "text": first[key].text} for key in keys[: 3 - len(asked)]]


def search_cards(
    cards: list[EvidenceCard], query: str, allowed_codes: set[str], answers: SituationAnswers
) -> list[EvidenceCard]:
    """작은 코퍼스의 태그 검색. 무관한 입력은 임의로 최상위 카드를 반환하지 않는다."""
    if len(query) > 400:
        raise ValueError("검색 표현은 400자 이하여야 합니다.")
    text = query.casefold()
    scored = [
        (sum(len(tag) for tag in card.tags if tag.casefold() in text), card)
        for card in cards
        if card.status == "approved" and card.challenge_code in allowed_codes and answers.supports(card.challenge_code)
    ]
    scored = [(score, card) for score, card in scored if score > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].card_id))
    return [card for _, card in scored[:3]]


class CardSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_code: str
    evidence_card_id: str


class SelectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[CardSelection] = Field(max_length=3)


def validate_selection(
    output: object, retrieved: list[EvidenceCard], allowed_codes: set[str], answers: SituationAnswers
) -> list[tuple[str, EvidenceCard]]:
    parsed = SelectionOutput.model_validate(output)
    selected: list[tuple[str, EvidenceCard]] = []
    seen: set[str] = set()
    by_id = {card.card_id: card for card in retrieved if card.status == "approved"}
    for item in parsed.selections:
        card = by_id.get(item.evidence_card_id)
        if (
            item.challenge_code not in allowed_codes
            or item.challenge_code in seen
            or card is None
            or card.challenge_code != item.challenge_code
            or not answers.supports(item.challenge_code)
        ):
            raise ValueError("검색된 승인 근거와 현재 허용 후보에 맞지 않는 제안입니다.")
        seen.add(item.challenge_code)
        selected.append((item.challenge_code, card))
    return selected
