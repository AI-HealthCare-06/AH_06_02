"""예측 접수·조회 (PRED-01·02·03). 추론과 SHAP 은 ai_worker 가 하고 app 은 접수와 저장 결과 조회만 한다."""

import logging
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.core.errors import AppError, ErrorCode
from app.core.utils.common import age_from_birth_year
from app.dtos.predictions import (
    ContributionItem,
    DiseaseContributions,
    DiseaseProbability,
    PredictionAccepted,
    PredictionContributionsResponse,
    PredictionFailure,
    PredictionStatusResponse,
)
from app.models.health_records import HealthRecord
from app.models.predictions import Disease, Prediction, PredictionStatus
from app.models.users import User
from app.repositories.health_record_repository import HealthRecordRepository
from app.repositories.prediction_repository import PredictionRepository
from app.services.model_artifact import (
    FACTOR_DICTIONARY_VERSION,
    ArtifactLoader,
    ArtifactSource,
    ModelArtifact,
    is_modifiable,
)
from app.services.prediction_queue import PredictionQueue, RedisPredictionQueue

logger = logging.getLogger(__name__)

DISEASES = (Disease.DIABETES, Disease.HYPERTENSION)
#: 질환 → (진단 컬럼, 복약 컬럼). 둘 중 하나라도 있으면 그 질환은 예측하지 않는다
DIAGNOSIS_FIELDS = {
    Disease.DIABETES: ("dm_diagnosed", "dm_medication"),
    Disease.HYPERTENSION: ("htn_diagnosed", "htn_medication"),
}
PROBABILITY_FIELDS = {Disease.DIABETES: "dm_probability", Disease.HYPERTENSION: "htn_probability"}
#: 모델 입력 중 users 에서 오는 값. 나머지는 같은 이름의 health_records 컬럼에서 읽는다
PROFILE_FIELDS = ("birth_year", "sex")
CONTRIBUTION_UNIT = "probability"
#: PRED-02 failure 로 나가는 문구. 큐·워커 내부 사정(스택·경로·원시 건강값)은 싣지 않는다
RETRY_FAILURE = {"code": "INTERNAL_ERROR", "message": "예측에 실패했습니다. 다시 시도해주세요.", "retryable": True}
#: 누락 안내 문구용. 목록에 없는 입력은 이름만 쓴다
FEATURE_LABELS = {
    "age": "나이",
    "sex": "성별",
    "bmi": "체질량지수",
    "waist_cm": "허리둘레",
    "smoking_current": "현재 흡연",
    "alcohol_frequency": "음주 빈도",
    "alcohol_amount": "1회 음주량",
    "walking_days": "걷기 일수",
    "walking_minutes": "1회 걷기 시간",
    "strength_days": "근력운동 일수",
    "family_history_dm": "당뇨 가족력",
    "family_history_htn": "고혈압 가족력",
    "sitting_minutes": "좌식시간",
    "dining_out_freq": "외식 빈도",
    "vegetable_frequency": "채소 섭취 빈도",
}


def target_diseases(user: User) -> list[Disease]:
    """진단·복약 이력이 없는 질환만 예측한다 (REQ-PRED-007)."""
    return [disease for disease in DISEASES if not any(getattr(user, field) for field in DIAGNOSIS_FIELDS[disease])]


def model_inputs(user: User, record: HealthRecord, names: list[str]) -> dict[str, Any]:
    """접수 시점의 모델 입력값. 학습 데이터를 만든 규칙(scripts/model/preprocess_knhanes.py)과 같게 맞춘다."""
    values: dict[str, Any] = {}
    for name in names:
        if name == "age":
            value: Any = age_from_birth_year(user.birth_year)
        elif name == "sex":
            value = str(user.sex) if user.sex is not None else None
        else:
            value = getattr(record, name, None)
        if isinstance(value, bool):
            value = int(value)
        elif isinstance(value, Decimal):
            value = float(value)
        values[name] = value
    # 학습 전처리와 같다: 최근 1년 비음주(빈도 1)면 음주량 비해당을 0 으로, 걷기 0일이면 걷기 시간 0
    if values.get("alcohol_frequency") == 1 and "alcohol_amount" in values and values["alcohol_amount"] is None:
        values["alcohol_amount"] = 0
    if values.get("walking_days") == 0 and "walking_minutes" in values:
        values["walking_minutes"] = 0
    return values


class PredictionService:
    def __init__(self, artifact_source: ArtifactSource | None = None, queue: PredictionQueue | None = None) -> None:
        self.artifact_source = artifact_source or ArtifactLoader().load
        self.queue = queue or RedisPredictionQueue()
        self.predictions = PredictionRepository()
        self.health_records = HealthRecordRepository()

    async def submit(self, user: User, health_record_id: int) -> PredictionAccepted:
        """PRED-01. 검사를 모두 통과하면 pending 으로 저장하고 접수만 한다."""
        record = await self.health_records.get_for_user(health_record_id, user.id)
        if record is None:
            raise AppError(ErrorCode.HLTH_RECORD_NOT_FOUND)
        diseases = target_diseases(user)
        if not diseases:
            raise AppError(ErrorCode.PRED_ALL_DIAGNOSED)
        if any(getattr(user, field) is None for field in PROFILE_FIELDS):
            raise AppError(ErrorCode.HLTH_PROFILE_INCOMPLETE)

        # 필수 입력은 활성 모델이 적어 둔 목록이라 아티팩트를 먼저 읽는다
        artifact = self._active_artifact()
        names = self._required_features(artifact, diseases)
        values = model_inputs(user, record, names)
        missing = [name for name in names if values[name] is None]
        if missing:
            listed = ", ".join(f"{FEATURE_LABELS.get(name, name)}({name})" for name in missing)
            raise AppError(ErrorCode.PRED_INPUT_INSUFFICIENT, message=f"필수 입력이 누락되었습니다: {listed}.")

        prediction = await self.predictions.create_pending(
            user_id=user.id,
            health_record_id=record.id,
            job_id=f"job-{uuid4().hex}",
            model_version=artifact.model_version,
            input_snapshot={"diseases": [str(disease) for disease in diseases], "features": values},
        )
        try:
            await self.queue.enqueue(prediction.id, prediction.job_id)
        except Exception:
            # 적재에 실패하면 워커가 영영 집어 가지 않는다. 영구 pending 대신 failed 로 남기고 500 이다
            logger.exception("예측 큐 적재 실패: prediction_id=%s", prediction.id)
            await self.predictions.mark_failed(prediction.id, RETRY_FAILURE)
            raise AppError(ErrorCode.INTERNAL_ERROR) from None
        return PredictionAccepted(
            prediction_id=prediction.id,
            job_id=prediction.job_id,
            status=prediction.status,
            model_version=prediction.model_version,
            model_experimental=artifact.experimental,
            poll_url=f"/api/v1/predictions/{prediction.id}",
        )

    def _active_artifact(self) -> ModelArtifact:
        artifact = self.artifact_source()
        if artifact is None:
            logger.error("예측 접수 불가: 활성 모델 아티팩트가 없다")
            raise AppError(ErrorCode.INTERNAL_ERROR)
        return artifact

    @staticmethod
    def _required_features(artifact: ModelArtifact, diseases: list[Disease]) -> list[str]:
        """대상 질환 모델들의 입력을 합친다. 입력 목록이 없으면 모델이 준비되지 않은 것이다."""
        names: list[str] = []
        for disease in diseases:
            features = artifact.features.get(disease)
            if not features:
                logger.error("예측 접수 불가: %s 모델의 입력 목록이 아티팩트에 없다", disease)
                raise AppError(ErrorCode.INTERNAL_ERROR)
            names.extend(name for name in features if name not in names)
        return names

    async def status(self, user: User, prediction_id: int) -> PredictionStatusResponse:
        """PRED-02."""
        prediction = await self._owned(user, prediction_id)
        results = None
        failure = None
        if prediction.status == PredictionStatus.DONE:
            results = [
                DiseaseProbability(disease=disease, probability=float(probability))
                for disease, probability in self._probabilities(prediction).items()
            ]
        elif prediction.status == PredictionStatus.FAILED and prediction.failure:
            failure = PredictionFailure.model_validate(prediction.failure)
        return PredictionStatusResponse(
            prediction_id=prediction.id,
            job_id=prediction.job_id,
            status=prediction.status,
            model_version=prediction.model_version,
            model_experimental=self._experimental(prediction),
            results=results,
            failure=failure,
        )

    async def contributions(
        self, user: User, prediction_id: int, disease: Disease | None, limit: int
    ) -> PredictionContributionsResponse:
        """PRED-03. 질환마다 limit 을 따로 적용한다."""
        prediction = await self._owned(user, prediction_id)
        diseases = None
        if prediction.status == PredictionStatus.DONE:
            included = list(self._probabilities(prediction))
            if disease is not None:
                # 예측에서 빠진 질환을 빈 배열로 주면 아직 안 끝난 것과 구별되지 않는다
                if disease not in included:
                    raise AppError(ErrorCode.PRED_NOT_FOUND)
                included = [disease]
            diseases = [
                DiseaseContributions(
                    disease=item,
                    items=[
                        ContributionItem(
                            factor_key=row.factor_key,
                            contribution=float(row.contribution),
                            direction=row.direction,
                            rank=row.rank,
                            modifiable=is_modifiable(row.factor_key),
                        )
                        for row in await self.predictions.contributions(prediction.id, item, limit)
                    ],
                )
                for item in included
            ]
        return PredictionContributionsResponse(
            prediction_id=prediction.id,
            status=prediction.status,
            model_version=prediction.model_version,
            model_experimental=self._experimental(prediction),
            factor_dictionary_version=FACTOR_DICTIONARY_VERSION,
            contribution_unit=CONTRIBUTION_UNIT,
            diseases=diseases,
        )

    async def _owned(self, user: User, prediction_id: int) -> Prediction:
        prediction = await self.predictions.get_for_user(prediction_id, user.id)
        if prediction is None:
            # 남의 예측도 없는 것과 같이 404 다. 403 은 그 ID 가 있다는 사실을 드러낸다
            raise AppError(ErrorCode.NOT_FOUND)
        return prediction

    @staticmethod
    def _probabilities(prediction: Prediction) -> dict[Disease, Decimal]:
        """완료된 예측에 들어 있는 미진단 질환과 그 확률."""
        result: dict[Disease, Decimal] = {}
        for disease in DISEASES:
            value = getattr(prediction, PROBABILITY_FIELDS[disease])
            if value is not None:
                result[disease] = value
        return result

    def _experimental(self, prediction: Prediction) -> bool | None:
        """서빙 ID 는 학습 연도까지 해시하므로 같은 model_version 이면 같은 아티팩트다.

        다르면(모델 교체 뒤 이전 예측) 알 수 없어 None 이고 응답에서 빠진다. false 로 채우지 않는다.
        """
        artifact = self.artifact_source()
        if artifact is None or artifact.model_version != prediction.model_version:
            return None
        return artifact.experimental
