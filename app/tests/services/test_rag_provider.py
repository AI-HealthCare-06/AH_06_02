"""실제 API 호출 없이 전송 형식·미완료·거절 응답을 확인한다."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Config
from app.services.challenge_selections import decision_schema
from app.services.rag_cards import SituationAnswers, load_cards
from app.services.rag_provider import OpenAISelectionProvider, failure_label


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
            "evening_walk",
            "housework",
            "squat",
            "wall_pushup",
            "stand_call",
            "screen_break",
            "sweet_drink",
            "late_snack",
            "home_alcohol",
            "alcohol_free",
            "postpone_drinks",
            "first_cig",
            "smoke_free_home",
            "quit_reason",
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


def test_default_model_is_gpt_4o_and_key_is_masked() -> None:
    settings = Config(_env_file=None, OPENAI_API_KEY=SecretStr("sk-test-secret"))  # type: ignore[call-arg]
    assert settings.OPENAI_MODEL == "gpt-4o"
    assert "sk-test-secret" not in repr(settings) and "sk-test-secret" not in str(settings.model_dump())
    with pytest.raises(ValidationError):
        Config(_env_file=None, OPENAI_MODEL="m" * 33)  # type: ignore[call-arg]


def _completed(text: str) -> httpx.Response:
    return httpx.Response(
        200, json={"status": "completed", "output": [{"content": [{"type": "output_text", "text": text}]}]}
    )


@pytest.mark.asyncio
async def test_decide_forces_the_enum_schema_at_zero_temperature() -> None:
    sent: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return _completed('{"selections": []}')

    provider = OpenAISelectionProvider("test-key", "gpt-4o", httpx.MockTransport(handle))
    schema = decision_schema({"CH_DELAY_FIRST_CIG": ["C43"]})
    assert await provider.decide({"conversation": []}, schema) == {"selections": []}
    assert sent["model"] == "gpt-4o" and sent["temperature"] == 0.0 and sent["store"] is False
    assert sent["text"]["format"]["strict"] is True
    assert sent["text"]["format"]["schema"] == schema


@pytest.mark.asyncio
async def test_chat_is_free_text_with_the_conversation() -> None:
    sent: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return _completed("보통 몇 시에 일어나세요?")

    provider = OpenAISelectionProvider("test-key", "gpt-4o", httpx.MockTransport(handle))
    messages = [
        {"role": "user", "content": "아침 담배"},
        {"role": "assistant", "content": "네"},
        {"role": "user", "content": "응"},
    ]
    assert await provider.chat({"candidates": []}, messages) == "보통 몇 시에 일어나세요?"
    assert "text" not in sent and sent["temperature"] == 0.5
    assert [m["role"] for m in sent["input"]] == ["system", "system", "user", "assistant", "user"]


@pytest.mark.asyncio
async def test_rejected_key_never_reaches_errors_or_repr() -> None:
    sent: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        sent.update(model=json.loads(request.content)["model"], auth=request.headers["Authorization"])
        return httpx.Response(401, json={"error": {"code": "invalid_api_key", "type": "invalid_request_error"}})

    provider = OpenAISelectionProvider("sk-test-secret", "gpt-4o", httpx.MockTransport(handle))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        await provider.chat({"candidates": []}, [{"role": "user", "content": "식후 걷기"}])
    assert sent == {"model": "gpt-4o", "auth": "Bearer sk-test-secret"}
    assert failure_label(caught.value) == "HTTPStatusError 401"
    assert "sk-test-secret" not in str(caught.value) and "sk-test-secret" not in repr(provider)
