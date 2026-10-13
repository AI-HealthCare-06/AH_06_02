from typing import Any

from app.models.predictions import Disease, Prediction, PredictionContribution, PredictionStatus


class PredictionRepository:
    """predictions·prediction_contributions 접근. 쓰기는 A 만 한다. 대시보드는 완료(done) 예측만 본다."""

    def __init__(self) -> None:
        self._model = Prediction

    async def create_pending(
        self,
        *,
        user_id: int,
        health_record_id: int,
        job_id: str,
        model_version: str,
        input_snapshot: dict[str, Any],
    ) -> Prediction:
        return await self._model.create(
            user_id=user_id,
            health_record_id=health_record_id,
            job_id=job_id,
            status=PredictionStatus.PENDING,
            model_version=model_version,
            input_snapshot=input_snapshot,
        )

    async def mark_failed(self, prediction_id: int, failure: dict[str, Any]) -> None:
        """아직 pending 인 예측만 failed 로 바꾼다. 이미 끝난 결과는 덮어쓰지 않는다."""
        await self._model.filter(id=prediction_id, status=PredictionStatus.PENDING).update(
            status=PredictionStatus.FAILED, failure=failure
        )

    async def get_for_user(self, prediction_id: int, user_id: int) -> Prediction | None:
        """본인 예측만 돌려준다. 남의 예측은 없는 것과 똑같이 None 이다."""
        return await self._model.get_or_none(id=prediction_id, user_id=user_id)

    async def contributions(self, prediction_id: int, disease: Disease, limit: int) -> list[PredictionContribution]:
        """질환 안 rank 순으로 limit 개."""
        return (
            await PredictionContribution.filter(prediction_id=prediction_id, disease=disease)
            .order_by("rank", "id")
            .limit(limit)
        )

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
