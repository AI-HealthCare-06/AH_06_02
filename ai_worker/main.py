"""예측 워커. Redis pred:queue 에서 작업을 BRPOP 으로 받아 추론하고 predictions 에 반영한다.

    python -m ai_worker.main

모델은 시작할 때 한 번 읽는다(explainer 도 이때 만든다). 모델을 못 읽어도 워커는 떠 있고,
들어온 작업을 재시도 불가 실패로 기록해 영구 pending 을 만들지 않는다.
"""

import asyncio
import json
import signal
from pathlib import Path

from redis.asyncio import Redis
from tortoise import Tortoise

from ai_worker.core.logger import setup_logger
from ai_worker.tasks.inference import ModelUnavailableError, ServingModels, load_serving_models
from ai_worker.tasks.predict import process_job
from app.core import config
from app.core.db.databases import TORTOISE_ORM

logger = setup_logger()
#: BRPOP 대기 초. 종료 신호를 이 간격 안에 알아챈다
POP_TIMEOUT_SECONDS = 5


def load_models() -> ServingModels | ModelUnavailableError:
    try:
        models = load_serving_models(Path(config.MODEL_ARTIFACT_PATH), Path(config.MODEL_DIR))
    except ModelUnavailableError as exc:
        logger.error("예측 모델을 읽지 못했다. 작업은 실패로 기록한다: %s", exc)
        return exc
    logger.info("예측 모델 준비: %s (%s)", models.model_version, ", ".join(sorted(models.diseases)))
    return models


async def run(stop: asyncio.Event) -> None:
    models = await asyncio.to_thread(load_models)
    await Tortoise.init(config=TORTOISE_ORM)
    redis = Redis.from_url(config.REDIS_URL)
    logger.info("예측 큐 대기: %s", config.PREDICTION_QUEUE_KEY)
    try:
        while not stop.is_set():
            item = await redis.brpop([config.PREDICTION_QUEUE_KEY], timeout=POP_TIMEOUT_SECONDS)
            if item is None:
                continue
            try:
                payload = json.loads(item[1])
            except (TypeError, ValueError):
                logger.error("예측 작업을 해석하지 못해 버린다")
                continue
            if not isinstance(payload, dict):
                logger.error("예측 작업 형식이 아니라 버린다")
                continue
            try:
                outcome = await process_job(payload, models)
            except Exception:
                # DB 연결 오류 등. 작업은 pending 으로 남는다. 복구(재적재) 전략은 후속 작업이다
                logger.exception("예측 작업 처리 중 오류: prediction_id=%s", payload.get("prediction_id"))
                continue
            if outcome is not None:
                logger.info("예측 %s: prediction_id=%s", outcome.status, outcome.prediction_id)
    finally:
        await redis.aclose()
        await Tortoise.close_connections()


def main() -> None:
    async def entry() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await run(stop)

    asyncio.run(entry())


if __name__ == "__main__":
    main()
