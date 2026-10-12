from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.dependencies.security import get_request_user
from app.dtos.envelope import ok
from app.dtos.predictions import PredictionCreateRequest
from app.models.predictions import Disease
from app.models.users import User
from app.services.predictions import PredictionService

prediction_router = APIRouter(prefix="/predictions", tags=["predictions"])


def get_prediction_service() -> PredictionService:
    return PredictionService()


@prediction_router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_prediction(
    request: PredictionCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[PredictionService, Depends(get_prediction_service)],
) -> dict[str, Any]:
    """PRED-01 예측 접수. 추론 완료가 아니라 접수했다는 뜻의 202 다."""
    accepted = await service.submit(user, request.health_record_id)
    return ok(accepted.model_dump(mode="json"))


@prediction_router.get("/{prediction_id}", status_code=status.HTTP_200_OK)
async def get_prediction(
    prediction_id: Annotated[int, Path(gt=0)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[PredictionService, Depends(get_prediction_service)],
) -> dict[str, Any]:
    """PRED-02 예측 상태·결과 조회."""
    return ok((await service.status(user, prediction_id)).model_dump(mode="json", exclude_none=True))


@prediction_router.get("/{prediction_id}/contributions", status_code=status.HTTP_200_OK)
async def get_prediction_contributions(
    prediction_id: Annotated[int, Path(gt=0)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[PredictionService, Depends(get_prediction_service)],
    disease: Annotated[Disease | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> dict[str, Any]:
    """PRED-03 기여요인 조회."""
    result = await service.contributions(user, prediction_id, disease, limit)
    return ok(result.model_dump(mode="json", exclude_none=True))
