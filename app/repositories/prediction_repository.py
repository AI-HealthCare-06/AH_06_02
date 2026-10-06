from app.models.predictions import Prediction, PredictionStatus


class PredictionRepository:
    """predictions 읽기 전용. 대시보드는 완료(done) 예측만 본다."""

    def __init__(self) -> None:
        self._model = Prediction

    async def latest_done_with(self, user_id: int, probability_field: str, limit: int) -> list[Prediction]:
        """해당 질환 확률이 있는 done 예측을 최신순으로 limit 개."""
        return (
            await self._model.filter(
                user_id=user_id,
                status=PredictionStatus.DONE,
                **{f"{probability_field}__isnull": False},
            )
            .order_by("-predicted_at", "-id")
            .limit(limit)
        )

    async def done_for_records(self, user_id: int, health_record_ids: list[int]) -> list[Prediction]:
        """기록별 done 예측. 오래된 것부터 돌려줘서 같은 기록의 마지막 예측이 뒤에 온다."""
        if not health_record_ids:
            return []
        return await self._model.filter(
            user_id=user_id,
            status=PredictionStatus.DONE,
            health_record_id__in=health_record_ids,
        ).order_by("predicted_at", "id")
