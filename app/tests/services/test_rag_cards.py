"""운영 승인이 없는 근거를 검색·추천에 쓰지 않는지 확인한다."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.rag_cards import (
    ANSWER_FIELDS,
    QUESTION_TEXT,
    SUPPORTED_CODES,
    EvidenceCard,
    SituationAnswers,
    load_cards,
    questions_for,
    search_cards,
    validate_selection,
)

CORPUS = Path(__file__).resolve().parents[3] / "docs/01_planning/chatbot/cards-20261026.json"


def approved_cards() -> list[EvidenceCard]:
    """승인자 표기를 테스트용으로 바꾼 운영 카드."""
    return [
        card.model_copy(update={"status": "approved", "approved_by": "테스트 fixture"}) for card in load_cards(CORPUS)
    ]


def draft_cards() -> list[EvidenceCard]:
    """승인 전 상태로 되돌린 운영 카드. 승인 안 된 카드는 쓰지 않는지 확인할 때 쓴다."""
    return [card.model_copy(update={"status": "draft", "approved_by": None}) for card in load_cards(CORPUS)]


def test_draft_cards_are_never_retrieved() -> None:
    card = EvidenceCard(
        card_id="C01",
        version="20261012-v1",
        status="draft",
        challenge_code="CH_WALK_AFTER_MEAL",
        tags=["식후", "점심"],
        guidance="가능한 식사 시간에 움직임을 계획해보세요.",
        source_url="https://www.who.int/news-room/fact-sheets/detail/physical-activity",
        source_section="How much physical activity is recommended?",
        reviewed_at="2026-10-12",
    )
    assert search_cards([card], "점심 식후 걷기", {"CH_WALK_AFTER_MEAL"}, SituationAnswers(meal_walk="both")) == []


def test_search_respects_available_codes_and_fixed_goal_answers() -> None:
    cards = approved_cards()
    result = search_cards(
        cards, "비가 와서 실내에서 식후에 걸어요", {"CH_WALK_AFTER_MEAL"}, SituationAnswers(meal_walk="both_indoor")
    )
    assert "C03" in [card.card_id for card in result]
    assert len(result) <= 3
    assert search_cards(cards, "식후 점심", {"CH_WALK_AFTER_MEAL"}, SituationAnswers(meal_walk="dinner_only")) == []
    assert search_cards(cards, "버스 출퇴근", {"CH_WALK_AFTER_MEAL"}, SituationAnswers(transit="yes")) == []
    assert search_cards(cards, "회사에서 앉아", {"CH_STAND_HOURLY"}, SituationAnswers(movement_breaks="limited")) == []


def test_questions_never_exceed_three_or_repeat_known_answers() -> None:
    codes = {"CH_WALK_AFTER_MEAL", "CH_WALK_ONE_STOP", "CH_STAND_HOURLY"}
    assert len(questions_for(codes, SituationAnswers(), [])) == 3
    assert questions_for(codes, SituationAnswers(), ["meal_walk", "transit", "movement_breaks"]) == []
    assert [q["key"] for q in questions_for(codes, SituationAnswers(meal_walk="both"), [])] == [
        "transit",
        "movement_breaks",
    ]
    with pytest.raises(ValueError):
        questions_for(codes, SituationAnswers(), ["meal_walk", "meal_walk"])


@pytest.mark.parametrize(
    "selection",
    [
        {"challenge_code": "NEW_WALK", "evidence_card_id": "C01"},
        {"challenge_code": "CH_WALK_AFTER_MEAL", "evidence_card_id": "C05"},
        {"challenge_code": "CH_WALK_AFTER_MEAL", "evidence_card_id": "missing"},
        {"challenge_code": "CH_WALK_AFTER_MEAL", "evidence_card_id": "C01", "target_value": 5},
    ],
)
def test_invalid_generated_selection_is_rejected(selection: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        validate_selection(
            {"selections": [selection]},
            approved_cards()[:1],
            {"CH_WALK_AFTER_MEAL"},
            SituationAnswers(meal_walk="both"),
        )


def test_unapproved_evidence_and_duplicate_codes_are_rejected() -> None:
    item = {"challenge_code": "CH_WALK_AFTER_MEAL", "evidence_card_id": "C01"}
    answers = SituationAnswers(meal_walk="both")
    with pytest.raises(ValueError):
        validate_selection({"selections": [item]}, draft_cards(), {"CH_WALK_AFTER_MEAL"}, answers)
    with pytest.raises(ValueError):
        validate_selection({"selections": [item, item]}, approved_cards(), {"CH_WALK_AFTER_MEAL"}, answers)
    with pytest.raises(ValidationError):
        EvidenceCard.model_validate(approved_cards()[0].model_dump() | {"approved_by": None})


NEW_CODES = {
    "CH_STAIRS": "stairs",
    "CH_STRENGTH_10": "strength",
    "CH_NO_DRINK_TODAY": "no_drink",
    "CH_NO_SMOKE_TODAY": "no_smoke",
}


@pytest.mark.parametrize(("code", "field"), NEW_CODES.items())
def test_remaining_phase1_codes_are_supported_only_after_a_yes(code: str, field: str) -> None:
    assert not SituationAnswers().supports(code)
    assert not SituationAnswers.model_validate({field: "no"}).supports(code)
    assert SituationAnswers.model_validate({field: "yes"}).supports(code)


def test_activity_limit_answer_exists_only_for_activity_challenges() -> None:
    assert not SituationAnswers(stairs="limited").supports("CH_STAIRS")
    assert not SituationAnswers(strength="limited").supports("CH_STRENGTH_10")
    with pytest.raises(ValidationError):
        SituationAnswers.model_validate({"no_drink": "limited"})
    with pytest.raises(ValidationError):
        SituationAnswers.model_validate({"no_smoke": "limited"})


def test_questions_follow_the_codes_in_the_current_batch() -> None:
    assert [q["key"] for q in questions_for({"CH_STAIRS", "CH_STRENGTH_10"}, SituationAnswers(), [])] == [
        "stairs",
        "strength",
    ]
    assert [q["key"] for q in questions_for({"CH_NO_DRINK_TODAY"}, SituationAnswers(), [])] == ["no_drink"]
    assert [q["key"] for q in questions_for({"CH_NO_SMOKE_TODAY"}, SituationAnswers(), [])] == ["no_smoke"]


def test_every_supported_code_has_an_approved_card_in_the_corpus() -> None:
    # 승인 카드가 없는 코드는 검색에 걸리지 않아 대화형 추천이 늘 규칙 추천으로 돌아간다
    approved = {card.challenge_code for card in load_cards(CORPUS) if card.status == "approved" and card.approved_by}
    assert approved == SUPPORTED_CODES


def test_every_supported_code_has_its_own_question_and_answer_field() -> None:
    assert set(ANSWER_FIELDS) == SUPPORTED_CODES
    assert set(ANSWER_FIELDS.values()) == set(QUESTION_TEXT)
    assert set(QUESTION_TEXT) <= set(SituationAnswers.model_fields)
