"""예측 작업 큐 (PRED-01 → ai_worker). Redis 리스트 하나를 쓴다.

작업에는 prediction_id·job_id 만 싣는다. 건강값은 predictions.input_snapshot 에 있고 큐·로그에 싣지 않는다.
"""

import json
from typing import Protocol

from redis.asyncio import Redis

from app.core import config


class PredictionQueue(Protocol):
    async def enqueue(self, prediction_id: int, job_id: str) -> None: ...


def job_payload(prediction_id: int, job_id: str) -> str:
    return json.dumps({"prediction_id": prediction_id, "job_id": job_id})


class RedisPredictionQueue:
    """LPUSH 로 넣고 워커가 BRPOP 으로 꺼내 먼저 들어온 작업부터 처리한다."""

    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        self.url = url or config.REDIS_URL
        self.key = key or config.PREDICTION_QUEUE_KEY

    async def enqueue(self, prediction_id: int, job_id: str) -> None:
        client = Redis.from_url(self.url)
        try:
            await client.lpush(self.key, job_payload(prediction_id, job_id))
        finally:
            await client.aclose()
