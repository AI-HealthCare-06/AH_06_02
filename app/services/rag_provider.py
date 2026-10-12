"""외부 모델은 검색된 승인 카드의 키만 선택한다. 목표·설명 문구는 서버에서 정한다."""

import json
from typing import Any, Protocol

import httpx

from app.services.rag_cards import EvidenceCard, SelectionOutput, SituationAnswers


class SelectionProvider(Protocol):
    model_version: str

    async def select(self, cards: list[EvidenceCard], answers: SituationAnswers) -> object: ...


class OpenAISelectionProvider:
    def __init__(self, api_key: str, model: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not api_key or not model or len(model) > 32:
            raise ValueError("API 키와 저장 가능한 32자 이내 모델 식별자를 설정해주세요.")
        self._api_key = api_key
        self.model_version = model
        self._transport = transport

    async def select(self, cards: list[EvidenceCard], answers: SituationAnswers) -> object:
        payload: dict[str, Any] = {
            "model": self.model_version,
            "store": False,
            "max_output_tokens": 800,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "전달한 근거 카드에서만 챌린지 키와 카드 ID를 선택하세요. "
                        "목표량이나 새로운 코드를 생성하지 마세요. "
                        "적합한 후보가 없으면 빈 selections를 반환하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "answers": answers.model_dump(),
                            "cards": [
                                {"card_id": c.card_id, "challenge_code": c.challenge_code, "guidance": c.guidance}
                                for c in cards
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "challenge_selection",
                    "strict": True,
                    "schema": SelectionOutput.model_json_schema(),
                }
            },
        }
        async with httpx.AsyncClient(timeout=12, transport=self._transport) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            result = response.json()
        if result.get("status") != "completed":
            raise ValueError("모델 응답이 완료되지 않았습니다.")
        texts = []
        for message in result.get("output", []):
            for content in message.get("content", []):
                if content.get("type") == "refusal":
                    raise ValueError("모델이 제안을 보류했습니다.")
                if content.get("type") == "output_text":
                    texts.append(content["text"])
        if len(texts) != 1:
            raise ValueError("검증할 모델 출력이 없습니다.")
        return json.loads(texts[0])
