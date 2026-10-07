import logging
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from dateutil.relativedelta import relativedelta

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.core.validators.health_validators import health_value_violations
from app.dtos.health_records import (
    DailyHealthRecordInput,
    DetailHealthRecordInput,
    HealthRecordItem,
    SimpleHealthRecordInput,
)
from app.models.health_records import HealthRecord, InputMode
from app.models.users import User
from app.repositories.health_record_repository import HealthRecordRepository
from app.services.impacts import refresh_impact_from_health_record

logger = logging.getLogger(__name__)

#: 조회 가능한 기간의 상한. 기본값이 아니라 이보다 앞선 날짜는 받지 않는다 (REQ-HLTH-005)
LOOKBACK_MONTHS = 12

#: 간편·정밀 입력은 users 프로필의 이 값이 있어야 저장한다 (HLTH-01)
PROFILE_FIELDS = ("birth_year", "sex", "height_cm")


def resolve_period(start_date: date | None, end_date: date | None, today: date | None = None) -> tuple[date, date]:
    """조회 기간을 KST 달력 날짜로 정한다. HLTH-02와 DASH-02가 같은 규칙을 쓴다.

    비어 있는 쪽은 기본값으로 채운다. 12개월 밖이나 뒤집힌 기간은 잘라내지 않고 400으로 돌려준다.
    """
    today = today or datetime.now(config.TIMEZONE).date()
    earliest = today - relativedelta(months=LOOKBACK_MONTHS)
    start = start_date or earliest
    end = end_date or today

    if start < earliest:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message=f"최근 {LOOKBACK_MONTHS}개월 안의 기록만 조회할 수 있습니다.",
            extra={"fields": [{"field": "start_date", "min": earliest.isoformat(), "max": today.isoformat()}]},
        )
    if start > end:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message="시작일은 종료일보다 늦을 수 없습니다.",
            extra={"fields": [{"field": "start_date", "min": earliest.isoformat(), "max": end.isoformat()}]},
        )
    return start, end


def period_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """[start 00:00, end 다음 날 00:00) KST. DATETIME은 KST naive로 저장되어 있다."""
    return (
        datetime.combine(start, time.min, tzinfo=config.TIMEZONE),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=config.TIMEZONE),
    )


def calculate_bmi(weight_kg: Decimal, height_cm: Decimal) -> Decimal:
    """키·몸무게로 서버에서 계산한다 (HLTH-01). 저장 정밀도 DECIMAL(4,1)에 맞춘다."""
    height_m = Decimal(height_cm) / 100
    return (Decimal(weight_kg) / (height_m * height_m)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


class HealthRecordService:
    def __init__(self) -> None:
        self.repo = HealthRecordRepository()

    async def create(
        self,
        user: User,
        data: SimpleHealthRecordInput | DetailHealthRecordInput | DailyHealthRecordInput,
    ) -> HealthRecord:
        """HLTH-01. 새 행으로 쌓고 기존 기록은 건드리지 않는다 (REQ-HLTH-004)."""
        if data.input_mode != InputMode.DAILY and any(getattr(user, field) is None for field in PROFILE_FIELDS):
            raise AppError(ErrorCode.HLTH_PROFILE_INCOMPLETE)

        values = data.model_dump(exclude={"input_mode"}, exclude_none=True)
        violations = health_value_violations(values)
        if violations:
            raise AppError(ErrorCode.HLTH_VALUE_OUT_OF_RANGE, extra={"fields": violations})

        if values.get("weight_kg") is not None and user.height_cm is not None:
            values["bmi"] = calculate_bmi(values["weight_kg"], user.height_cm)

        record = await self.repo.create(
            user_id=user.id,
            recorded_at=datetime.now(config.TIMEZONE),
            input_mode=data.input_mode,
            **values,
        )
        # 위협도 갱신은 건강기록 저장이 커밋된 뒤에 부른다. repo.create 는 트랜잭션 밖이라 반환 시점에 이미 커밋돼 있다.
        # 갱신은 D 가 소유한 부수 작업이라, 실패해도 사용자가 입력한 기록을 되돌리지 않는다.
        # 예외는 삼키고 로그만 남긴다 (A·D 합의 계약). 다음 입력이나 재예측 때 다시 갱신된다.
        # daily 입력은 impacts.py 가 안에서 거르므로 여기서 따로 분기하지 않는다.
        try:
            await refresh_impact_from_health_record(user.id, record.id)
        except Exception:
            logger.exception("위협도 갱신 실패 · user_id=%s health_record_id=%s", user.id, record.id)
        return record

    async def list_records(
        self,
        user: User,
        start_date: date | None,
        end_date: date | None,
        page: int,
        size: int,
    ) -> dict[str, Any]:
        """HLTH-02. 본인 기록만 recorded_at 내림차순으로 돌려준다."""
        start, end = resolve_period(start_date, end_date)
        lower, upper = period_bounds(start, end)
        items, total = await self.repo.page_by_period(user.id, lower, upper, offset=(page - 1) * size, limit=size)
        return {
            "items": [HealthRecordItem.model_validate(item).model_dump(mode="json") for item in items],
            "total": total,
            "page": page,
            "size": size,
        }
