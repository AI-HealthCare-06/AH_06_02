from datetime import date

from app.dtos.dashboard import (
    DashboardSummaryResponse,
    DashboardTrendsResponse,
    LatestHealthRecord,
    RiskSummary,
    TrendMeasurements,
    TrendPoint,
    TrendRisk,
)
from app.models.predictions import Disease
from app.models.users import User
from app.repositories.health_record_repository import HealthRecordRepository
from app.repositories.prediction_repository import PredictionRepository
from app.services.health_records import period_bounds, resolve_period

#: 질환 -> (users 진단 여부 컬럼, predictions 확률 컬럼)
DISEASE_COLUMNS: dict[Disease, tuple[str, str]] = {
    Disease.DIABETES: ("dm_diagnosed", "dm_probability"),
    Disease.HYPERTENSION: ("htn_diagnosed", "htn_probability"),
}


def undiagnosed_diseases(user: User) -> list[Disease]:
    """진단받은 질환의 예측은 보여주지 않는다 (REQ-PRED-007)."""
    return [disease for disease, (diagnosed, _) in DISEASE_COLUMNS.items() if not getattr(user, diagnosed)]


class DashboardService:
    def __init__(self) -> None:
        self.health_records = HealthRecordRepository()
        self.predictions = PredictionRepository()

    async def summary(self, user: User) -> DashboardSummaryResponse:
        """DASH-01. 미진단 질환의 최신 위험도와 직전 예측 대비 변화 (REQ-DASH-001)."""
        risks: list[RiskSummary] = []
        for disease in undiagnosed_diseases(user):
            _, column = DISEASE_COLUMNS[disease]
            latest = await self.predictions.latest_done_with(user.id, column, limit=2)
            if not latest:
                continue
            current = getattr(latest[0], column)
            # 확률은 0~1, 변화량은 percentage points
            delta = float((current - getattr(latest[1], column)) * 100) if len(latest) > 1 else None
            risks.append(
                RiskSummary(
                    disease=disease,
                    probability=float(current),
                    delta=delta,
                    predicted_at=latest[0].predicted_at,
                )
            )

        record = await self.health_records.get_latest(user.id)
        return DashboardSummaryResponse(
            # 두 질환 모두 진단이거나 아직 완료된 예측이 없으면 risks 가 비고 false 다
            prediction_available=bool(risks),
            risks=risks,
            latest_health_record=(
                LatestHealthRecord(health_record_id=record.id, recorded_at=record.recorded_at) if record else None
            ),
        )

    async def trends(self, user: User, start_date: date | None, end_date: date | None) -> DashboardTrendsResponse:
        """DASH-02. 같은 기간 축의 건강수치와 위험도 (REQ-DASH-002). health_record_id 로 연결한다."""
        start, end = resolve_period(start_date, end_date)
        records = await self.health_records.list_by_period(user.id, *period_bounds(start, end))
        # 오름차순이라 같은 기록에 예측이 여럿이면 마지막 것이 남는다
        prediction_by_record = {
            prediction.health_record_id: prediction
            for prediction in await self.predictions.done_for_records(user.id, [record.id for record in records])
        }
        diseases = undiagnosed_diseases(user)

        points: list[TrendPoint] = []
        for record in records:
            risks: list[TrendRisk] = []
            prediction = prediction_by_record.get(record.id)
            if prediction is not None:
                for disease in diseases:
                    probability = getattr(prediction, DISEASE_COLUMNS[disease][1])
                    if probability is not None:
                        risks.append(
                            TrendRisk(
                                disease=disease,
                                probability=float(probability),
                                predicted_at=prediction.predicted_at,
                            )
                        )
            points.append(
                TrendPoint(
                    recorded_at=record.recorded_at,
                    health_record_id=record.id,
                    measurements=TrendMeasurements.model_validate(record),
                    risks=risks,
                )
            )
        return DashboardTrendsResponse(points=points)
