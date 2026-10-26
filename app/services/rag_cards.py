"""승인 근거 검색과 고정 원형 추천 검증. 정책·목표·보상은 생성하지 않는다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

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
QUESTION_TEXT = {
    "meal_walk": "점심과 저녁 식후에 각각 10분씩 걷는 것이 가능한가요?",
    "transit": "대중교통 이용일에 한 정거장 먼저 내려 걷는 것이 가능한가요?",
    "movement_breaks": "앉아서 지내는 중간에 3분씩 하루 세 번 움직일 수 있나요?",
    "stairs": "평소 다니는 곳에 계단이 있고, 하루 한 번 계단으로 올라갈 수 있나요?",
    "strength": "하루 10분 맨몸 근력 운동을 할 시간과 공간이 있나요?",
    "no_drink": "술을 마시지 않는 날을 정해서 그날 하루 지킬 수 있나요?",
    "no_smoke": "피우지 않는 날을 정해서 그날 하루 시도해 볼 수 있나요?",
    "evening_walk": "저녁에 20분 이어서 걸을 시간이 있나요?",
    "housework": "청소처럼 몸을 쓰는 집안일을 15분 이어서 할 수 있나요?",
    "squat": "의자를 뒤에 두고 앉았다 일어나기를 15회 할 수 있나요?",
    "wall_pushup": "벽에 손을 짚고 팔굽혀펴기를 10회 할 수 있나요?",
    "stand_call": "전화 통화를 서서 할 수 있나요?",
    "screen_break": "영상을 볼 때 30분마다 일어날 수 있나요?",
    "sweet_drink": "오늘 단 음료 대신 물을 마실 수 있나요?",
    "late_snack": "저녁 식사 뒤로 야식을 먹지 않을 수 있나요?",
    "home_alcohol": "오늘 집에 술을 사두지 않을 수 있나요?",
    "alcohol_free": "저녁 식사 때 술 대신 다른 음료를 마실 수 있나요?",
    "postpone_drinks": "오늘 술 약속이 있다면 미루거나 술 없는 만남으로 바꿀 수 있나요?",
    "first_cig": "아침에 일어나 첫 담배를 30분 미룰 수 있나요?",
    "smoke_free_home": "집 안과 차 안에서 피우지 않을 수 있나요?",
    "quit_reason": "담배를 끊고 싶은 이유를 한 줄 적어 볼 수 있나요?",
}
#: "예"라고 답하면 후보로 남는 질문. 식후 걷기·한 정거장·움직임 휴식은 답 종류가 달라 따로 본다
YES_ANSWER_CODES = {
    code: field
    for code, field in ANSWER_FIELDS.items()
    if code not in {"CH_WALK_AFTER_MEAL", "CH_WALK_ONE_STOP", "CH_STAND_HOURLY"}
}


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
    if len(asked) > 3 or len(set(asked)) != len(asked) or any(key not in QUESTION_TEXT for key in asked):
        raise ValueError("질문 기록은 알려진 질문을 중복 없이 최대 세 개까지 사용합니다.")
    if answers.activity_limited:
        return []
    values = answers.model_dump()
    wanted = {ANSWER_FIELDS[code] for code in codes & SUPPORTED_CODES}
    keys = [key for key in QUESTION_TEXT if key in wanted and values[key] == "unknown" and key not in asked]
    return [{"key": key, "text": QUESTION_TEXT[key]} for key in keys[: 3 - len(asked)]]


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
