"""외부 모델 호출.

- select: 대화형 추천. 승인 카드의 키만 고른다
- judge: 질의 챗봇 판단 모델. 후보 라벨 하나를 고르는 1토큰의 logprobs 로 라벨별 확률만 돌려준다

어느 쪽이든 서버가 다시 검사한다. 목표 단계표·설명 원문·보상은 서버에서 정한다.
"""

import json
import math
from typing import Any, Protocol

import httpx

from app.services.rag_cards import EvidenceCard, SelectionOutput, SituationAnswers

OPENAI_BASE_URL = "https://api.openai.com/v1"

JUDGE_INSTRUCTIONS = (
    "당신은 챌린지 판단기입니다. answers 는 사용자가 선택형 질문에 직접 고른 답이고, "
    "cohort 는 지난 수행 요약, cards 는 각 후보의 운영 근거입니다. 이것을 보고 candidates 중 지금 이 사용자에게 "
    "가장 알맞은 챌린지 하나를 고르세요. 그 후보의 label 한 글자만 출력하고 다른 글자는 쓰지 마세요."
)

#: 판단 온도. 같은 입력에 같은 분포를 내도록 0 으로 둔다
JUDGE_TEMPERATURE = 0.0
#: logprobs 로 받을 상위 토큰 수(API 최대값). 후보는 질문 수(최대 3개)만큼이라 모두 담긴다
JUDGE_TOP_LOGPROBS = 20
#: Responses API 의 최소 출력 토큰. 실제로는 첫 토큰(라벨)만 읽는다
JUDGE_MAX_TOKENS = 16


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

    async def judge(self, context: dict[str, Any], labels: list[str]) -> dict[str, float]: ...


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

    async def judge(self, context: dict[str, Any], labels: list[str]) -> dict[str, float]:
        """2단계 판단 모델. 첫 출력 토큰의 상위 logprobs 를 라벨별 확률로 바꾼다. 문장은 쓰지 않는다.

        context 의 candidates 에는 label 이 붙어 있다. 라벨이 아닌 토큰은 버리고, 라벨이 하나도 없으면 ValueError.
        """
        content = json.dumps(context, ensure_ascii=False, default=str)
        result = await self._call(
            [{"role": "system", "content": JUDGE_INSTRUCTIONS}, {"role": "user", "content": content}],
            None,
            JUDGE_MAX_TOKENS,
            JUDGE_TEMPERATURE,
            top_logprobs=JUDGE_TOP_LOGPROBS,
        )
        first = self._first_token(result)
        probabilities: dict[str, float] = {}
        for item in first.get("top_logprobs") or [first]:
            token = str(item.get("token", "")).strip()
            if token in labels:
                probabilities[token] = probabilities.get(token, 0.0) + math.exp(float(item["logprob"]))
        if not probabilities:
            raise ValueError("판단 모델 출력에 후보 라벨이 없습니다.")
        return probabilities

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
        *,
        top_logprobs: int | None = None,
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
        if top_logprobs is not None:
            payload["top_logprobs"] = top_logprobs
            payload["include"] = ["message.output_text.logprobs"]
        async with httpx.AsyncClient(timeout=12, transport=self._transport) as client:
            response = await client.post(self._url, json=payload, headers={"Authorization": f"Bearer {self._api_key}"})
            response.raise_for_status()
            result: dict[str, Any] = response.json()
        if result.get("status") != "completed":
            raise ValueError("모델 응답이 완료되지 않았습니다.")
        return result

    @classmethod
    def _first_token(cls, result: dict[str, Any]) -> dict[str, Any]:
        """출력 문장의 첫 토큰 logprobs 항목. 응답에 logprobs 가 없으면 ValueError."""
        cls._text(result)
        for message in result.get("output", []):
            for item in message.get("content", []):
                if item.get("type") == "output_text" and item.get("logprobs"):
                    first: dict[str, Any] = item["logprobs"][0]
                    return first
        raise ValueError("판단 모델 응답에 logprobs 가 없습니다.")

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
