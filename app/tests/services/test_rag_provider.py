"""실제 API 호출 없이 전송 형식·미완료·거절 응답을 확인한다."""

import json
from pathlib import Path

import httpx
import pytest

from app.services.rag_cards import SituationAnswers, load_cards
from app.services.rag_provider import OpenAISelectionProvider


@pytest.mark.asyncio
async def test_provider_sends_only_closed_answers_and_cards() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.openai.com/v1/responses"
        payload = json.loads(request.content)
        assert payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        context = json.loads(payload["input"][1]["content"])
        assert set(context) == {"answers", "cards"}
        assert set(context["answers"]) == {
            "meal_walk",
            "transit",
            "movement_breaks",
            "stairs",
            "strength",
            "no_drink",
            "no_smoke",
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": '{"selections": []}'}]}],
            },
        )

    provider = OpenAISelectionProvider("test-key", "fixture-model", httpx.MockTransport(handle))
    path = Path(__file__).resolve().parents[3] / "docs/01_planning/chatbot/cards-20261026.json"
    assert await provider.select(load_cards(path)[:1], SituationAnswers(meal_walk="both")) == {"selections": []}


@pytest.mark.parametrize(
    "response",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": [{"content": [{"type": "refusal", "refusal": "보류"}]}]},
        {"status": "completed", "output": [{"content": [{"type": "output_text", "text": "잘못된 JSON"}]}]},
    ],
)
@pytest.mark.asyncio
async def test_incomplete_or_refused_response_cannot_be_selected(response: dict[str, object]) -> None:
    provider = OpenAISelectionProvider(
        "test-key", "fixture-model", httpx.MockTransport(lambda request: httpx.Response(200, json=response))
    )
    with pytest.raises(ValueError):
        await provider.select([], SituationAnswers())
