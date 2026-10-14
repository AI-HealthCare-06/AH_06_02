"""예측 작업 하나를 처리한다 (docs/01_planning/api-predictions.md 저장·워커 계약).

- 같은 job 이 다시 와도 pending 이 아니면 건너뛴다. 저장은 행 잠금 안에서 다시 확인한다.
- 대상 질환 결과와 전체 factor 기여도를 한 transaction 으로 저장한 뒤 done. 한 질환이라도 실패하면 failed.
- done 커밋 뒤 D 의 refresh_impact_from_prediction 을 부른다. 그 오류로 예측을 실패로 바꾸지 않는다.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from tortoise.transactions import in_transaction

from ai_worker.tasks.inference import ModelUnavailableError, ServingModels
from app.core import config
from app.models.health_records import HealthRecord
from app.models.predictions import (
    ContributionDirection,
    Disease,
    Prediction,
    PredictionContribution,
    PredictionStatus,
)
from app.models.users import User
from app.services.predictions import PROBABILITY_FIELDS, RETRY_FAILURE

logger = logging.getLogger(__name__)

#: 모델 파일이 없거나 접수 때와 다른 모델이면 다시 시도해도 같다
MODEL_FAILURE = {
    "code": "INTERNAL_ERROR",
    "message": "지금은 예측 모델을 사용할 수 없습니다. 잠시 후 다시 시도해주세요.",
    "retryable": False,
}


@dataclass(frozen=True)
class Outcome:
    status: str
    prediction_id: int


def worker_inputs(snapshot_features: dict[str, Any], user: User, record: HealthRecord) -> dict[str, Any]:
    """접수 스냅샷에 워커가 계산하는 bmi·age 를 덮는다.

    모델 스펙: bmi = weight_kg / (height_cm/100)², age = KST 올해 - 출생연도.
    키·출생연도는 users, 체중은 health_records 에서 읽는다.
    """
    if record.weight_kg is None or user.height_cm is None or user.birth_year is None:
        raise ValueError("bmi·age 를 계산할 체중·키·출생연도가 없다")
    height_m = float(user.height_cm) / 100
    features = dict(snapshot_features)
    features["bmi"] = float(record.weight_kg) / (height_m * height_m)
    features["age"] = datetime.now(config.TIMEZONE).year - user.birth_year
    return features


def _decimal(value: float, places: int) -> Decimal:
    return Decimal(str(round(value, places)))


async def process_job(payload: dict[str, Any], models: ServingModels | ModelUnavailableError) -> Outcome | None:
    """작업 하나. 처리할 것이 없으면 None. models 가 ModelUnavailableError 이면 모델 없이 실패로 기록한다."""
    prediction_id = payload.get("prediction_id")
    job_id = payload.get("job_id")
    if type(prediction_id) is not int or not isinstance(job_id, str):
        logger.error("잘못된 예측 작업을 버린다")
        return None
    prediction = await Prediction.get_or_none(id=prediction_id)
    if prediction is None or prediction.job_id != job_id:
        logger.warning("예측 작업과 맞는 행이 없다: prediction_id=%s", prediction_id)
        return None
    if prediction.status != PredictionStatus.PENDING:
        # 같은 job 재전달. 결과·기여도를 다시 만들지 않는다
        return None

    try:
        results = await _infer(prediction, models)
    except ModelUnavailableError as exc:
        logger.error("예측 실패(모델): prediction_id=%s %s", prediction_id, exc)
        return await _fail(prediction_id, MODEL_FAILURE)
    except Exception:
        # 원시 건강값을 남기지 않도록 예외 메시지만 남긴다
        logger.exception("예측 실패: prediction_id=%s", prediction_id)
        return await _fail(prediction_id, RETRY_FAILURE)

    async with in_transaction():
        locked = await Prediction.select_for_update().get_or_none(id=prediction_id)
        if locked is None or locked.status != PredictionStatus.PENDING:
            return None
        await PredictionContribution.filter(prediction_id=prediction_id).delete()
        rows: list[PredictionContribution] = []
        for disease, (probability, contributions) in results.items():
            setattr(locked, PROBABILITY_FIELDS[disease], _decimal(probability, 4))
            rows.extend(
                PredictionContribution(
                    prediction_id=prediction_id,
                    disease=disease,
                    factor_key=item["factor_key"],
                    contribution=_decimal(item["contribution"], 5),
                    direction=ContributionDirection(item["direction"]),
                    rank=item["rank"],
                )
                for item in contributions
            )
        await PredictionContribution.bulk_create(rows)
        # grade 경계값은 아직 정해지지 않았다(REQ-PRED-004). metabolic_count 는 이번 범위 밖이다
        locked.status = PredictionStatus.DONE
        locked.failure = None
        locked.predicted_at = datetime.now(config.TIMEZONE)
        await locked.save()

    await _refresh_impact(prediction.user_id, prediction_id)
    return Outcome(PredictionStatus.DONE, prediction_id)


async def _infer(
    prediction: Prediction, models: ServingModels | ModelUnavailableError
) -> dict[Disease, tuple[float, list[dict[str, Any]]]]:
    """대상 질환마다 확률과 전체 기여도. 한 질환이라도 실패하면 예외로 끝나 부분 결과를 남기지 않는다."""
    if isinstance(models, ModelUnavailableError):
        raise models
    if prediction.model_version != models.model_version:
        raise ModelUnavailableError(f"접수 모델 {prediction.model_version} ≠ 워커 모델 {models.model_version}")
    snapshot: dict[str, Any] = dict(prediction.input_snapshot or {})
    diseases = [Disease(name) for name in snapshot.get("diseases", [])]
    if not diseases:
        raise ValueError("입력 스냅샷에 대상 질환이 없다")
    user = await User.get(id=prediction.user_id)
    record = await HealthRecord.get(id=prediction.health_record_id, user_id=prediction.user_id)
    features = worker_inputs(dict(snapshot.get("features") or {}), user, record)
    results = {}
    for disease in diseases:
        model = models.diseases.get(str(disease))
        if model is None:
            raise ModelUnavailableError(f"{disease} 모델이 없다")
        results[disease] = model.predict(features)
    return results


async def _fail(prediction_id: int, failure: dict[str, Any]) -> Outcome | None:
    async with in_transaction():
        locked = await Prediction.select_for_update().get_or_none(id=prediction_id)
        if locked is None or locked.status != PredictionStatus.PENDING:
            return None
        locked.status = PredictionStatus.FAILED
        locked.failure = failure
        await locked.save()
    return Outcome(PredictionStatus.FAILED, prediction_id)


async def _refresh_impact(user_id: int, prediction_id: int) -> None:
    from app.services.impacts import refresh_impact_from_prediction

    try:
        await refresh_impact_from_prediction(user_id, prediction_id)
    except Exception:
        # 저장된 예측은 그대로 done 이다. 위협도 동기화 재시도는 후속 작업이다
        logger.exception("위협도 갱신 실패: prediction_id=%s", prediction_id)
