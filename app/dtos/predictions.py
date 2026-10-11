"""예측 API(PRED-01·02·03) 요청·응답. 계약은 docs/01_planning/api-spec.md B 탭이다.

값이 없는 필드는 null 로 싣지 않고 뺀다(공통 규칙). 라우터는 exclude_none 으로 내보낸다.
"""

from typing import Annotated

from pydantic import BaseModel, Field

from app.models.predictions import ContributionDirection, Disease, PredictionStatus


class PredictionCreateRequest(BaseModel):
    """PRED-01. user_id 는 토큰에서만 얻는다."""

    health_record_id: Annotated[int, Field(gt=0)]


class PredictionAccepted(BaseModel):
    prediction_id: int
    job_id: str
    status: PredictionStatus
    model_version: str
    model_experimental: bool
    poll_url: str


class DiseaseProbability(BaseModel):
    disease: Disease
    probability: float


class PredictionFailure(BaseModel):
    code: str
    message: str
    retryable: bool


class PredictionStatusResponse(BaseModel):
    """PRED-02. pending·failed 에는 results 가, failed 가 아니면 failure 가 없다."""

    prediction_id: int
    job_id: str
    status: PredictionStatus
    model_version: str
    #: 저장된 모델 버전이 활성 아티팩트와 같을 때만 안다. 다르면 뺀다
    model_experimental: bool | None = None
    results: list[DiseaseProbability] | None = None
    failure: PredictionFailure | None = None


class ContributionItem(BaseModel):
    factor_key: str
    contribution: float
    direction: ContributionDirection
    rank: int
    modifiable: bool


class DiseaseContributions(BaseModel):
    disease: Disease
    items: list[ContributionItem]


class PredictionContributionsResponse(BaseModel):
    """PRED-03. pending·failed 에는 diseases 가 없다."""

    prediction_id: int
    status: PredictionStatus
    model_version: str
    model_experimental: bool | None = None
    factor_dictionary_version: str
    contribution_unit: str
    diseases: list[DiseaseContributions] | None = None
