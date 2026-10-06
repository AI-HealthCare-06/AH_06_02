"""챌린지 추천 (REQ-CHLG-001·002·006).

미진단 질환은 개인 SHAP 위협도, 진단 질환은 global normalized_score × behavior_weight 로 factor_score 를 낸다.
두 경로 모두 같은 매핑(challenges.factor_key ↔ 공략 대상 monsters.factor_keys)을 쓰고 중복 챌린지는 합친다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from tortoise.expressions import Q

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    Challenge,
    ChallengeRecommendation,
    CooldownChoice,
    Monster,
    RecommendationAction,
    RecommendationSourceType,
    UserAttackCycle,
    UserChallenge,
    UserChallengeStatus,
)
from app.models.health_records import HealthRecord
from app.models.predictions import Disease, Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.repositories.health_record_repository import HealthRecordRepository
from app.services.attack_cycles import AttackCycleService, today_kst
from app.services.model_artifact import ArtifactLoader, ArtifactSource, ModelArtifact, personal_threat_score

MAX_CARDS = 3

#: 1단계 추천에서 빼는 활성 카드. 비활성 2개(스파이크)는 is_enabled 로 빠진다.
PHASE1_EXCLUDED_CODES = frozenset(
    {
        # 음주·흡연 욕구 발생형. 예정 기회를 미리 만들 수 없다
        "CH_ONE_LESS_GLASS",
        "CH_WATER_BETWEEN",
        "CH_DELAY_5MIN",
        # 구매 발생형 (challenge-factor-map.md)
        "CH_CHECK_LABEL",
        # 관찰 완료 규칙 미승인 (challenge-candidates.md)
        "CH_COUNT_DOWN",
        # 보너스. factor_key 가 없어 캐릭터에 매핑되지 않는다
        "CH_WATER_8",
        "CH_SLEEP_7H",
        # 예정 이용일을 받는 계약이 없어 시작할 수 없다. 마스터 행·난이도는 그대로 두고 계약이 생기면 다시 넣는다
        "CH_WALK_ONE_STOP",
    }
)

#: 추천 적용 보류 factor. 진단자·미진단자 공통으로 후보에서 뺀다.
#: 위협도나 예측값을 0 으로 덮어쓰지 않고 후보에서만 제외한다.
HELD_FACTORS = frozenset(
    {
        # 범주별 SHAP 부호가 섞여 단조 risk condition 이 없다 (factor-scales.md 65·74행)
        "sodium_behavior",
    }
)

#: 행동으로 바꾸기 어려운 factor. threat_eligible 이어도 weight 대상이 아니다 (factor-scales.md 51행)
NON_BEHAVIORAL_FACTORS = frozenset({"age", "sex", "family_history_dm", "family_history_htn"})

#: factor-scales.md 55행 표에서 수치 조건이 없거나 D 확인·결정 대기로 남은 factor.
#: 조건을 지어내지 않고 진단자 경로에서 건너뛴다.
CONDITION_PENDING_FACTORS = frozenset(
    {
        "alcohol_frequency",  # 챌린지와 cutoff 최종표 D 확인 필요
        "alcohol_amount",  # 양별 제한 D 결정 대기
        "bmi_high",  # 수치 cutoff 미정
        "waist_high",  # 수치 cutoff 미정
        "physical_activity_low",  # 수치 cutoff 와 걷기 시간 병행 여부 미정
        "strength_activity_low",  # 수치 cutoff 미정
        "sedentary_time_high",  # 수치 cutoff 미정
        "vegetable_intake_low",  # 제품 입력 미확정
    }
)

DISEASE_DIAGNOSED_FIELD = {Disease.DIABETES: "dm_diagnosed", Disease.HYPERTENSION: "htn_diagnosed"}
DISEASE_PROBABILITY_FIELD = {Disease.DIABETES: "dm_probability", Disease.HYPERTENSION: "htn_probability"}

COOLDOWN_DAYS = {CooldownChoice.DAYS_7: 7, CooldownChoice.DAYS_30: 30}
#: 같은 챌린지를 이만큼 연속 거절하면 재추천 시점을 고른다 (REQ-CHLG-006)
REJECTS_BEFORE_COOLDOWN = 3


def behavior_weight(factor_key: str, record: HealthRecord | None) -> int | None:
    """진단자 behavior_weight 0/1 (factor-scales.md 51·55행). None 은 미평가·조건 미정으로 추천하지 않는다.

    매핑 챌린지가 실제로 있는지는 후보 필터가 따로 본다.
    """
    if factor_key in NON_BEHAVIORAL_FACTORS:
        return 0
    if factor_key in CONDITION_PENDING_FACTORS:
        return None
    if factor_key == "smoking_current":
        # sm_presnt=1(현재 흡연)이면 1. 결측은 미평가
        if record is None or record.smoking_current is None:
            return None
        return 1 if record.smoking_current else 0
    return None


def check_cooldown(action: RecommendationAction, streak: int, cooldown_choice: CooldownChoice | None) -> None:
    """거절이 3회 연속일 때만 재추천 시점을 고른다. 해당없음에는 쿨다운이 없다."""
    if action == RecommendationAction.REJECTED:
        if streak >= REJECTS_BEFORE_COOLDOWN and cooldown_choice is None:
            raise AppError(ErrorCode.CHLG_INVALID_COOLDOWN, message="다시 추천받을 시점을 골라주세요.")
        if streak < REJECTS_BEFORE_COOLDOWN and cooldown_choice is not None:
            raise AppError(ErrorCode.CHLG_INVALID_COOLDOWN, message="연속 3회 거절했을 때만 고를 수 있습니다.")
    elif action == RecommendationAction.NOT_APPLICABLE:
        if cooldown_choice is not None:
            raise AppError(ErrorCode.CHLG_INVALID_COOLDOWN, message="쿨다운은 거절할 때만 고를 수 있습니다.")
    else:
        raise AppError(ErrorCode.VALIDATION_ERROR)


def monster_diseases(monster: Monster) -> list[Disease]:
    scope = str(monster.disease_scope)
    if scope == Disease.DIABETES:
        return [Disease.DIABETES]
    if scope == Disease.HYPERTENSION:
        return [Disease.HYPERTENSION]
    return [Disease.DIABETES, Disease.HYPERTENSION]


async def phase1_candidates() -> list[Challenge]:
    """1단계 운영 후보. 비활성·제외 카드와 보류 factor 의 카드를 뺀다. 두 추천 경로가 같은 후보를 쓴다."""
    return [
        challenge
        for challenge in await Challenge.filter(is_enabled=True, factor_key__isnull=False).order_by("id")
        if challenge.code not in PHASE1_EXCLUDED_CODES and challenge.factor_key not in HELD_FACTORS
    ]


@dataclass
class FactorScore:
    score: float
    source_type: RecommendationSourceType


@dataclass
class GeneratedRecommendations:
    items: list[ChallengeRecommendation]
    challenges: dict[int, Challenge]
    cycle: UserAttackCycle
    monster: Monster
    model_version: str
    #: 실험 아티팩트로 낸 점수인지. 추천 가능 여부에는 영향을 주지 않고 표시만 한다
    model_experimental: bool


class RecommendationService:
    def __init__(self, artifact_source: ArtifactSource | None = None) -> None:
        self.artifact_source = artifact_source or ArtifactLoader().load
        self.cycles = AttackCycleService()
        self.health_records = HealthRecordRepository()

    async def generate(self, user: User, now: datetime | None = None) -> GeneratedRecommendations:
        """CHLG-01. 현재 주기의 공략 대상 factor 에 맞는 후보만 제시한다."""
        current = now or datetime.now(config.TIMEZONE)
        today = today_kst(current)
        artifact = self.artifact_source()
        if artifact is None:
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE)

        await self.cycles.close_expired(user.id, today, current)
        cycle = await self.cycles.get_or_create_for_recommendation(user.id)
        if cycle is None:
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE)
        monster = await self.cycles.target_monster(cycle)

        active = UserChallenge.filter(user_id=user.id, status=UserChallengeStatus.ACTIVE)
        slots = self.cycles.remaining_slots(
            cycle,
            active_in_cycle=await active.filter(cycle_id=cycle.id).count(),
            active_total=await active.count(),
            today=today,
        )
        if slots <= 0:
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE)

        blocked = await self._blocked_challenge_ids(user.id, current)
        candidates = [
            challenge
            for challenge in await phase1_candidates()
            if challenge.factor_key in monster.factor_keys and challenge.id not in blocked
        ]

        scores, missing_prediction = await self._factor_scores(user, monster, artifact)
        scored = [
            (challenge, scores[challenge.factor_key])
            for challenge in candidates
            if challenge.factor_key in scores and scores[challenge.factor_key].score > 0
        ]
        if not scored:
            if missing_prediction:
                raise AppError(ErrorCode.PRED_NOT_FOUND)
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE)

        scored.sort(key=lambda pair: (-pair[1].score, pair[0].context_priority or 255, pair[0].id))
        items: list[ChallengeRecommendation] = []
        for rank, (challenge, factor) in enumerate(scored[:MAX_CARDS], start=1):
            items.append(
                await ChallengeRecommendation.create(
                    user_id=user.id,
                    challenge_id=challenge.id,
                    cycle_id=cycle.id,
                    source_type=factor.source_type,
                    factor_key=challenge.factor_key,
                    factor_score=Decimal(str(round(factor.score, 5))),
                    rank=rank,
                    recommended_at=current,
                )
            )
        return GeneratedRecommendations(
            items=items,
            challenges={challenge.id: challenge for challenge, _ in scored},
            cycle=cycle,
            monster=monster,
            model_version=artifact.model_version,
            model_experimental=artifact.experimental,
        )

    async def _factor_scores(
        self, user: User, monster: Monster, artifact: ModelArtifact
    ) -> tuple[dict[str, FactorScore], bool]:
        """factor 별 최고 점수. 질환을 섞지 않고 각각 계산한 뒤 factor 단위로 큰 값을 쓴다 (REQ-PRED-007)."""
        record = await self.health_records.get_latest(user.id)
        prediction = await (
            Prediction.filter(user_id=user.id, status=PredictionStatus.DONE).order_by("-predicted_at", "-id").first()
        )
        scores: dict[str, FactorScore] = {}
        missing_prediction = False

        for disease in monster_diseases(monster):
            if getattr(user, DISEASE_DIAGNOSED_FIELD[disease]):
                path = self._global_scores(disease, monster, artifact, record)
            else:
                usable = (
                    prediction is not None
                    and prediction.model_version == artifact.model_version
                    and getattr(prediction, DISEASE_PROBABILITY_FIELD[disease]) is not None
                )
                if not usable or prediction is None:
                    # 저장된 예측을 다른 모델 버전 기준으로 다시 해석하지 않는다
                    missing_prediction = True
                    continue
                path = await self._personal_scores(disease, monster, artifact, prediction)
            for factor_key, score in path.items():
                if factor_key not in scores or score.score > scores[factor_key].score:
                    scores[factor_key] = score
        return scores, missing_prediction

    def _global_scores(
        self, disease: Disease, monster: Monster, artifact: ModelArtifact, record: HealthRecord | None
    ) -> dict[str, FactorScore]:
        result: dict[str, FactorScore] = {}
        normalized = artifact.global_scores.get(disease, {})
        for factor_key in monster.factor_keys:
            weight = behavior_weight(factor_key, record)
            if weight is None or factor_key not in normalized:
                continue
            result[factor_key] = FactorScore(normalized[factor_key] * weight, RecommendationSourceType.DIAGNOSIS_GLOBAL)
        return result

    async def _personal_scores(
        self, disease: Disease, monster: Monster, artifact: ModelArtifact, prediction: Prediction
    ) -> dict[str, FactorScore]:
        references = artifact.references.get(disease, {})
        contributions = await PredictionContribution.filter(
            prediction_id=prediction.id, disease=disease, factor_key__in=list(monster.factor_keys)
        )
        result: dict[str, FactorScore] = {}
        for contribution in contributions:
            reference = references.get(contribution.factor_key)
            if reference is None:
                continue
            score = personal_threat_score(float(contribution.contribution), reference)
            if score is not None:
                result[contribution.factor_key] = FactorScore(
                    float(score), RecommendationSourceType.PREDICTION_PERSONAL
                )
        return result

    async def _blocked_challenge_ids(self, user_id: int, now: datetime) -> set[int]:
        """진행 중이거나 쿨다운·수동 제외 중인 챌린지 (REQ-CHLG-006)."""
        active = await UserChallenge.filter(user_id=user_id, status=UserChallengeStatus.ACTIVE)
        held = await ChallengeRecommendation.filter(
            Q(exclude_until__gt=now) | Q(suppressed_until_manual=True), user_id=user_id
        )
        return {item.challenge_id for item in active} | {item.challenge_id for item in held}

    async def list_cards(self, user: User, page: int, size: int) -> tuple[list[dict[str, Any]], int]:
        """CHLG-02. 주기와 대상은 cycle_id 로 조인해 보여준다."""
        query = ChallengeRecommendation.filter(user_id=user.id)
        total = await query.count()
        rows = await query.order_by("-recommended_at", "rank", "-id").offset((page - 1) * size).limit(size)
        challenges = {item.id: item for item in await Challenge.filter(id__in=[row.challenge_id for row in rows])}
        targets = await self._cycle_targets({row.cycle_id for row in rows if row.cycle_id is not None})
        items = []
        for row in rows:
            challenge = challenges[row.challenge_id]
            items.append(
                {
                    "recommendation_id": row.id,
                    "challenge_id": row.challenge_id,
                    "title": challenge.title,
                    "description": challenge.description,
                    "factor_key": row.factor_key,
                    "rank": row.rank,
                    "difficulty": challenge.difficulty,
                    "verification_type": challenge.verification_type,
                    "context_label": challenge.context_label,
                    "cycle_id": row.cycle_id,
                    "target_monster": targets.get(row.cycle_id) if row.cycle_id is not None else None,
                    "proposed_goal": row.proposed_goal,
                    "action": row.action,
                    "cooldown_choice": row.cooldown_choice,
                    "exclude_until": row.exclude_until,
                }
            )
        return items, total

    async def _cycle_targets(self, cycle_ids: set[int]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for cycle in await UserAttackCycle.filter(id__in=list(cycle_ids)):
            monster = await self.cycles.target_monster(cycle)
            result[cycle.id] = target_monster_body(monster)
        return result

    async def act(
        self,
        user: User,
        recommendation_id: int,
        action: RecommendationAction,
        cooldown_choice: CooldownChoice | None,
        now: datetime | None = None,
    ) -> ChallengeRecommendation:
        """CHLG-03. 3회 연속 거절이면 재추천 시점을 사용자가 고른다 (REQ-CHLG-006).

        해당없음은 직접 다시 켤 때까지 추천에서 빼고, 연속 거절 집계에는 넣지 않는다.
        """
        current = now or datetime.now(config.TIMEZONE)
        row = await ChallengeRecommendation.get_or_none(id=recommendation_id, user_id=user.id)
        if row is None:
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)
        if row.action is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="이미 응답한 추천 카드입니다.")

        # 해당없음은 연속 거절을 늘리지도 끊지도 않는다. 거절과 수락만 본다
        previous = (
            await ChallengeRecommendation.filter(
                user_id=user.id,
                challenge_id=row.challenge_id,
                action__in=[RecommendationAction.REJECTED, RecommendationAction.ACCEPTED],
                id__not=row.id,
            )
            .order_by("-acted_at", "-id")
            .first()
        )
        streak = (
            previous.consecutive_reject_count if previous and previous.action == RecommendationAction.REJECTED else 0
        )

        if action == RecommendationAction.REJECTED:
            streak += 1
        check_cooldown(action, streak, cooldown_choice)

        row.action = action
        row.acted_at = current
        row.consecutive_reject_count = streak
        row.cooldown_choice = cooldown_choice
        if cooldown_choice in COOLDOWN_DAYS:
            row.exclude_until = current + timedelta(days=COOLDOWN_DAYS[cooldown_choice])
        if cooldown_choice == CooldownChoice.UNTIL_MANUAL or action == RecommendationAction.NOT_APPLICABLE:
            row.suppressed_until_manual = True
        await row.save()
        return row

    async def unsuppress(self, user: User, recommendation_id: int) -> ChallengeRecommendation:
        """CHLG-04. 직접 다시 켤 때까지 제외한 카드를 다시 켠다."""
        row = await ChallengeRecommendation.get_or_none(id=recommendation_id, user_id=user.id)
        if row is None:
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)
        row.suppressed_until_manual = False
        await row.save(update_fields=["suppressed_until_manual"])
        return row


def target_monster_body(monster: Monster) -> dict[str, Any]:
    return {"monster_id": monster.id, "code": monster.code, "name": monster.name}
