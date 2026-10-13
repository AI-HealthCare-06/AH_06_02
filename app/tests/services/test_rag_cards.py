"""운영 승인이 없는 근거를 검색·추천에 쓰지 않는지 확인한다."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.rag_cards import (
    EvidenceCard,
    SituationAnswers,
    load_cards,
    questions_for,
    search_cards,
    validate_selection,
)

CORPUS = Path(__file__).resolve().parents[3] / "docs/01_planning/chatbot/cards-draft-20261012.json"


def approved_cards() -> list[EvidenceCard]:
    """테스트에서만 승인 fixture로 만든다. 운영 JSON의 draft는 바꾸지 않는다."""
    return [
        card.model_copy(update={"status": "approved", "approved_by": "테스트 fixture"}) for card in load_cards(CORPUS)
    ]


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
        validate_selection({"selections": [item]}, load_cards(CORPUS), {"CH_WALK_AFTER_MEAL"}, answers)
    with pytest.raises(ValueError):
        validate_selection({"selections": [item, item]}, approved_cards(), {"CH_WALK_AFTER_MEAL"}, answers)
    with pytest.raises(ValidationError):
        EvidenceCard.model_validate(approved_cards()[0].model_dump() | {"approved_by": None})
