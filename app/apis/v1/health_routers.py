from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, status

from app.dependencies.security import get_request_user
from app.dtos.envelope import ok
from app.dtos.health_records import HealthRecordCreateRequest, HealthRecordCreateResponse
from app.models.users import User
from app.services.dashboard import DashboardService
from app.services.health_records import HealthRecordService

health_router = APIRouter(tags=["health"])


@health_router.post("/health-records", status_code=status.HTTP_201_CREATED)
async def create_health_record(
    request: Annotated[HealthRecordCreateRequest, Body()],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[HealthRecordService, Depends(HealthRecordService)],
) -> dict[str, Any]:
    """HLTH-01 건강정보 입력·시점별 저장."""
    record = await service.create(user=user, data=request)
    return ok(HealthRecordCreateResponse.model_validate(record).model_dump(mode="json"))


@health_router.get("/health-records", status_code=status.HTTP_200_OK)
async def list_health_records(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[HealthRecordService, Depends(HealthRecordService)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """HLTH-02 건강기록 목록·기간 조회."""
    return ok(await service.list_records(user=user, start_date=start_date, end_date=end_date, page=page, size=size))


@health_router.get("/dashboard/summary", status_code=status.HTTP_200_OK)
async def dashboard_summary(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[DashboardService, Depends(DashboardService)],
) -> dict[str, Any]:
    """DASH-01 대시보드 현재 위험도 요약."""
    return ok((await service.summary(user)).model_dump(mode="json"))


@health_router.get("/dashboard/trends", status_code=status.HTTP_200_OK)
async def dashboard_trends(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[DashboardService, Depends(DashboardService)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> dict[str, Any]:
    """DASH-02 위험도·건강수치 동일 기간 추이."""
    return ok((await service.trends(user, start_date=start_date, end_date=end_date)).model_dump(mode="json"))
