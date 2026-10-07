"""D 위협도 갱신 진입점. 추론은 하지 않고 같은 입력·버전의 저장 결과만 읽는다.

복수 factor의 대표값은 최댓값으로 두는 D 제출안이다. 연결 전 정책 문서의 합의 항목을 확인한다.
실측 스파이크 변환은 미확정이므로 승인된 scorer를 주입하기 전에는 미평가로 둔다.
"""

import math
from collections.abc import Callable
from datetime import datetime
from typing import TypedDict

from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import DefaultImpactSource, ImpactSource, Monster, MonsterState, UserMonster
from app.models.health_records import HealthRecord, InputMode
from app.models.predictions import Disease, Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.services.attack_cycles import lock_user
from app.services.model_artifact import ArtifactLoader, ArtifactSource, ModelArtifact, personal_threat_score
from app.services.recommendations import (
    DISEASE_DIAGNOSED_FIELD,
    DISEASE_PROBABILITY_FIELD,
    behavior_weight,
    monster_diseases,
    phase1_candidates,
)


class ImpactResult(TypedDict):
    updated: int
    sealed: list[str]


MeasuredScorer = Callable[[HealthRecord], int | None]


def impact_state(score: int | None, previous: UserMonster) -> MonsterState:
    """게임 외형 구간. v12의 40·70 경계를 중복 없이 처리한다. 질환 등급과는 별개다."""
    if previous.state == MonsterState.SEALED:
        return MonsterState.SEALED
    if score is None:
        return MonsterState.UNMEASURED
    if score == 0:
        had_impact = (previous.impact_score or 0) > 0 or previous.resolved_at is not None
        return MonsterState.RESOLVED if had_impact else MonsterState.NOT_CONTRIBUTING
    if score >= 70:
        return MonsterState.RAGE
    if score >= 40:
        return MonsterState.CAUTION
    return MonsterState.STABLE


class ImpactService:
    def __init__(
        self, artifact_source: ArtifactSource | None = None, measured_scorer: MeasuredScorer | None = None
    ) -> None:
        self.artifact_source = artifact_source or ArtifactLoader().load
        self.measured_scorer = measured_scorer

    async def from_health_record(self, user_id: int, health_record_id: int) -> ImpactResult:
        """C 저장 후 호출. daily는 제외하며 미완료 SHAP을 이전 입력으로 보충하지 않는다."""
        async with in_transaction():
            await lock_user(user_id)
            user, record = await self._input(user_id, health_record_id)
            if record.input_mode == InputMode.DAILY or not await self._is_current(record):
                return {"updated": 0, "sealed": []}
            artifact = self.artifact_source()
            prediction = None
            if artifact is not None:
                prediction = await self._latest_prediction(user_id, record.id, artifact.model_version)
            return await self._refresh(user, record, artifact, prediction)

    async def from_prediction(self, user_id: int, prediction_id: int) -> ImpactResult:
        """A가 예측과 전체 기여도를 커밋한 뒤 호출한다. 오래된 작업·다른 버전은 반영하지 않는다."""
        async with in_transaction():
            await lock_user(user_id)
            prediction = await Prediction.get_or_none(id=prediction_id)
            if prediction is None:
                raise AppError(ErrorCode.NOT_FOUND)
            if prediction.user_id != user_id:
                raise AppError(ErrorCode.FORBIDDEN)
            user, record = await self._input(user_id, prediction.health_record_id)
            artifact = self.artifact_source()
            if (
                record.input_mode == InputMode.DAILY
                or prediction.status != PredictionStatus.DONE
                or artifact is None
                or prediction.model_version != artifact.model_version
                or not await self._is_current(record)
            ):
                return {"updated": 0, "sealed": []}
            latest = await self._latest_prediction(user_id, record.id, artifact.model_version)
            if latest is None or latest.id != prediction.id:
                return {"updated": 0, "sealed": []}
            return await self._refresh(user, record, artifact, prediction)

    @staticmethod
    async def _input(user_id: int, record_id: int) -> tuple[User, HealthRecord]:
        user = await User.get_or_none(id=user_id)
        record = await HealthRecord.get_or_none(id=record_id)
        if user is None or record is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if record.user_id != user_id:
            raise AppError(ErrorCode.FORBIDDEN)
        return user, record

    @staticmethod
    async def _is_current(record: HealthRecord) -> bool:
        latest = (
            await HealthRecord.filter(user_id=record.user_id)
            .exclude(input_mode=InputMode.DAILY)
            .order_by("-recorded_at", "-id")
            .first()
        )
        return latest is not None and latest.id == record.id

    @staticmethod
    async def _latest_prediction(user_id: int, record_id: int, version: str) -> Prediction | None:
        return (
            await Prediction.filter(
                user_id=user_id, health_record_id=record_id, status=PredictionStatus.DONE, model_version=version
            )
            .order_by("-predicted_at", "-id")
            .first()
        )

    async def _refresh(
        self, user: User, record: HealthRecord, artifact: ModelArtifact | None, prediction: Prediction | None
    ) -> ImpactResult:
        contributions = await PredictionContribution.filter(prediction_id=prediction.id) if prediction else []
        signed = {(row.disease, row.factor_key): float(row.contribution) for row in contributions}
        mapped = {card.factor_key for card in await phase1_candidates()}
        updated = 0
        for monster in await Monster.filter(is_enabled=True).order_by("no"):
            if monster.default_impact_source == DefaultImpactSource.MEASURED:
                score = self.measured_scorer(record) if self.measured_scorer else None
                source = ImpactSource.MEASURED
            else:
                score, source = self._contribution_score(monster, user, record, artifact, prediction, signed, mapped)
            if score is None:
                # 결과 부재는 갱신 실패/미평가다. 이전 성공 이력을 현재 입력의 결과로 다시 저장하지 않는다.
                # 첫 측정 전은 도감이 기본 unmeasured로 보여준다. 기존 값은 그 출처와 함께 남긴다.
                continue
            if score is not None and (isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100):
                raise ValueError("위협도 scorer는 0~100 정수 또는 None을 반환해야 합니다.")
            row, _ = await UserMonster.get_or_create(user_id=user.id, monster_id=monster.id)
            previous_score = row.impact_score
            row.state = impact_state(score, row)
            current = datetime.now(config.TIMEZONE)
            if row.state == MonsterState.RESOLVED and row.resolved_at is None:
                row.resolved_at = current
            if row.state == MonsterState.SEALED and score is not None and previous_score is not None:
                if score > previous_score:
                    row.reawakened_at = current
            await UserMonster.filter(id=row.id).update(
                state=row.state,
                impact_score=score,
                impact_source=source,
                last_health_record_id=record.id,
                last_prediction_id=prediction.id if prediction and source == ImpactSource.CONTRIBUTION else None,
                resolved_at=row.resolved_at,
                reawakened_at=row.reawakened_at,
                updated_at=current,
            )
            updated += 1
        # 습관 졸업·새 봉인 조건은 미확정. 기존 봉인은 보존하되 새 봉인을 임의 판정하지 않는다.
        return {"updated": updated, "sealed": []}

    @staticmethod
    def _contribution_score(
        monster: Monster,
        user: User,
        record: HealthRecord,
        artifact: ModelArtifact | None,
        prediction: Prediction | None,
        signed: dict[tuple[Disease, str], float],
        mapped: set[str],
    ) -> tuple[int | None, ImpactSource]:
        if artifact is None:
            return None, ImpactSource.CONTRIBUTION
        values: list[tuple[int, ImpactSource]] = []
        for disease in monster_diseases(monster):
            diagnosed = getattr(user, DISEASE_DIAGNOSED_FIELD[disease])
            if diagnosed is None:
                return None, ImpactSource.CONTRIBUTION
            if not diagnosed and (
                prediction is None or getattr(prediction, DISEASE_PROBABILITY_FIELD[disease]) is None
            ):
                return None, ImpactSource.CONTRIBUTION
            for factor in monster.factor_keys:
                value, source = ImpactService._factor_score(
                    disease, factor, diagnosed, record, artifact, signed, mapped
                )
                if value is None:
                    # 메타데이터에 없는 질환×factor는 그 모델의 지원 factor가 아니다.
                    supported = (
                        factor in artifact.global_scores.get(disease, {})
                        if diagnosed
                        else factor in artifact.references.get(disease, {})
                    )
                    if supported:
                        return None, source
                    continue
                values.append((value, source))
        if not values:
            return None, ImpactSource.CONTRIBUTION
        # 합산으로 100 초과·factor 수에 따른 유리함을 만들지 않는다. 최대 요인을 대표값으로 제안한다.
        return max(values, key=lambda item: item[0])

    @staticmethod
    def _factor_score(
        disease: Disease,
        factor: str,
        diagnosed: bool,
        record: HealthRecord,
        artifact: ModelArtifact,
        signed: dict[tuple[Disease, str], float],
        mapped: set[str],
    ) -> tuple[int | None, ImpactSource]:
        if diagnosed:
            normalized = artifact.global_scores.get(disease, {}).get(factor)
            weight = behavior_weight(factor, record) if factor in mapped else 0
            if normalized is None or weight is None or not math.isfinite(normalized) or not 0 <= normalized <= 100:
                return None, ImpactSource.GLOBAL
            return math.floor(normalized * weight + 0.5), ImpactSource.GLOBAL
        reference = artifact.references.get(disease, {}).get(factor)
        value = signed.get((disease, factor))
        if reference is None or value is None:
            return None, ImpactSource.CONTRIBUTION
        return personal_threat_score(value, reference), ImpactSource.CONTRIBUTION


async def refresh_impact_from_health_record(user_id: int, health_record_id: int) -> ImpactResult:
    return await ImpactService().from_health_record(user_id, health_record_id)


async def refresh_impact_from_prediction(user_id: int, prediction_id: int) -> ImpactResult:
    return await ImpactService().from_prediction(user_id, prediction_id)
