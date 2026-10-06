from datetime import datetime
from typing import Any

from app.models.health_records import HealthRecord


class HealthRecordRepository:
    """health_records 쓰기는 C만 한다. 기록은 덮어쓰지 않고 쌓는다 (REQ-HLTH-004)."""

    def __init__(self) -> None:
        self._model = HealthRecord

    async def create(self, user_id: int, recorded_at: datetime, **values: Any) -> HealthRecord:
        return await self._model.create(user_id=user_id, recorded_at=recorded_at, **values)

    async def page_by_period(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[HealthRecord], int]:
        """[start, end) 구간의 본인 기록. recorded_at 내림차순."""
        query = self._model.filter(user_id=user_id, recorded_at__gte=start, recorded_at__lt=end)
        total = await query.count()
        items = await query.order_by("-recorded_at", "-id").offset(offset).limit(limit)
        return items, total

    async def list_by_period(self, user_id: int, start: datetime, end: datetime) -> list[HealthRecord]:
        """[start, end) 구간의 본인 기록. 추이 그래프용이라 recorded_at 오름차순."""
        return await self._model.filter(user_id=user_id, recorded_at__gte=start, recorded_at__lt=end).order_by(
            "recorded_at", "id"
        )

    async def get_latest(self, user_id: int) -> HealthRecord | None:
        return await self._model.filter(user_id=user_id).order_by("-recorded_at", "-id").first()
