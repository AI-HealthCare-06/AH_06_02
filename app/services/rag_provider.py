"""외부 모델 호출.

- select: 대화형 추천. 승인 카드의 키만 고른다
- chat: 질의 챗봇 1단계. 자유 대화 문장을 돌려준다
- decide: 질의 챗봇 2단계(디시전 모델). 서버가 만든 enum 스키마 안의 JSON 만 돌려준다

어느 쪽이든 서버가 다시 검사한다. 목표 단계표·설명 원문·보상은 서버에서 정한다.
"""

import json
from typing import Any, Protocol

import httpx

from app.services.rag_cards import EvidenceCard, SelectionOutput, SituationAnswers

OPENAI_BASE_URL = "https://api.openai.com/v1"

CHAT_INSTRUCTIONS = (
    "당신은 생활습관 챌린지 앱의 대화 도우미입니다. 사용자의 하루 일과·가능한 시간·상황을 자연스럽게 물어보며 "
    "어떤 챌린지가 맞을지 함께 찾습니다. "
    "소개할 수 있는 챌린지는 context 의 candidates 뿐이고, 설명은 pages 안에서만 하세요. "
    "새 챌린지를 만들거나 목표량·횟수·난이도·단계를 정하거나 바꾸겠다고 말하지 마세요. 목표는 앱이 정합니다. "
    "목표 숫자를 말할 때는 그 후보의 served_goal 값만 쓰세요. pages 의 단계표에는 다른 단계 값도 있습니다. "
    "진단하거나 질병·수치를 예방·치료·개선한다고 말하지 말고, 위험도나 확률을 언급하지 마세요. "
    "한 번에 3~4문장 이내의 한국어로 답하세요."
)

DECISION_INSTRUCTIONS = (
    "당신은 챌린지 선택기입니다. conversation·answers·cohort 를 보고 candidates 중 사용자에게 맞는 챌린지를 "
    "최대 3개 고르세요. challenge_code 는 candidates 의 코드만, evidence_card_ids 는 같은 challenge_code 의 cards 만 "
    "쓰세요. 목표 값은 고르지 않습니다(served_goal 은 앱이 정한 값입니다). "
    "reason 은 그 카드 guidance 를 근거로 사용자에게 건네는 존댓말 한 문장입니다. "
    "guidance 는 운영 기준 문장이니 그대로 옮기거나 '~라고 답한 경우', '~를 제안한다' 같은 말투를 따라 쓰지 마세요. "
    "숫자는 그 후보의 served_goal 값과 같을 때만 쓰고, 질병·치료·위험도·효과는 말하지 마세요. "
    "맞는 후보가 없으면 selections 를 비우세요."
)

#: 질의 챗봇 온도. 선택 단계는 같은 입력에 같은 결정을 내도록 0 으로 둔다
CHAT_TEMPERATURE = 0.5
DECISION_TEMPERATURE = 0.0


#: 구조화 출력이 받지 않을 수 있는 키. 길이는 서버가 다시 검사한다
UNSENT_SCHEMA_KEYS = frozenset({"maxLength", "minLength"})


def strict_schema(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {key: strict_schema(value) for key, value in schema.items() if key not in UNSENT_SCHEMA_KEYS}
    if isinstance(schema, list):
        return [strict_schema(item) for item in schema]
    return schema


def failure_label(exc: BaseException) -> str:
    """로그에 남길 실패 요약. 예외 종류와 HTTP 상태만 쓰고 요청·응답 본문과 헤더(키)는 담지 않는다."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{type(exc).__name__} {exc.response.status_code}"
    return type(exc).__name__


class SelectionProvider(Protocol):
    model_version: str

    async def select(self, cards: list[EvidenceCard], answers: SituationAnswers) -> object: ...


class ChatProvider(Protocol):
    model_version: str

    async def chat(self, context: dict[str, Any], messages: list[dict[str, str]]) -> str: ...

    async def decide(self, context: dict[str, Any], schema: dict[str, Any]) -> object: ...


class OpenAISelectionProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        base_url: str = OPENAI_BASE_URL,
    ) -> None:
        if not api_key or not model or len(model) > 32:
            raise ValueError("API 키와 저장 가능한 32자 이내 모델 식별자를 설정해주세요.")
        self._api_key = api_key
        self.model_version = model
        self._transport = transport
        self._url = base_url.rstrip("/") + "/responses"

    def __repr__(self) -> str:
        # 키가 디버그 출력·예외 메시지로 새지 않도록 모델만 보인다
        return f"OpenAISelectionProvider(model={self.model_version!r})"

    async def select(self, cards: list[EvidenceCard], answers: SituationAnswers) -> object:
        content = json.dumps(
            {
                "answers": answers.model_dump(),
                "cards": [
                    {"card_id": c.card_id, "challenge_code": c.challenge_code, "guidance": c.guidance} for c in cards
                ],
            },
            ensure_ascii=False,
        )
        system = (
            "전달한 근거 카드에서만 챌린지 키와 카드 ID를 선택하세요. "
            "목표량이나 새로운 코드를 생성하지 마세요. "
            "적합한 후보가 없으면 빈 selections를 반환하세요."
        )
        return await self._respond(system, content, "challenge_selection", SelectionOutput.model_json_schema(), 800)

    async def chat(self, context: dict[str, Any], messages: list[dict[str, str]]) -> str:
        """1단계 자유 대화. context 는 서버가 만든 후보·페이지뿐이고, messages 는 가린 대화다."""
        content = json.dumps(context, ensure_ascii=False, default=str)
        conversation = [{"role": m["role"], "content": m["content"]} for m in messages]
        result = await self._call(
            [
                {"role": "system", "content": CHAT_INSTRUCTIONS},
                {"role": "system", "content": f"context: {content}"},
                *conversation,
            ],
            None,
            400,
            CHAT_TEMPERATURE,
        )
        return self._text(result)

    async def decide(self, context: dict[str, Any], schema: dict[str, Any]) -> object:
        """2단계 디시전 모델. 출력은 schema(enum 으로 묶은 코드·카드) 안의 JSON 하나다."""
        content = json.dumps(context, ensure_ascii=False, default=str)
        result = await self._call(
            [{"role": "system", "content": DECISION_INSTRUCTIONS}, {"role": "user", "content": content}],
            {"type": "json_schema", "name": "challenge_decision", "strict": True, "schema": strict_schema(schema)},
            600,
            DECISION_TEMPERATURE,
        )
        return json.loads(self._text(result))

    async def _respond(
        self, system: str, content: str, schema_name: str, schema: dict[str, Any], max_tokens: int
    ) -> object:
        result = await self._call(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema},
            max_tokens,
            None,
        )
        return json.loads(self._text(result))

    async def _call(
        self,
        messages: list[dict[str, str]],
        text_format: dict[str, Any] | None,
        max_tokens: int,
        temperature: float | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_version,
            "store": False,
            "max_output_tokens": max_tokens,
            "input": messages,
        }
        if text_format is not None:
            payload["text"] = {"format": text_format}
        if temperature is not None:
            payload["temperature"] = temperature
        async with httpx.AsyncClient(timeout=12, transport=self._transport) as client:
            response = await client.post(self._url, json=payload, headers={"Authorization": f"Bearer {self._api_key}"})
            response.raise_for_status()
            result: dict[str, Any] = response.json()
        if result.get("status") != "completed":
            raise ValueError("모델 응답이 완료되지 않았습니다.")
        return result

    @staticmethod
    def _text(result: dict[str, Any]) -> str:
        texts = []
        for message in result.get("output", []):
            for item in message.get("content", []):
                if item.get("type") == "refusal":
                    raise ValueError("모델이 응답을 보류했습니다.")
                if item.get("type") == "output_text":
                    texts.append(item["text"])
        if len(texts) != 1:
            raise ValueError("검증할 모델 출력이 없습니다.")
        return str(texts[0])
