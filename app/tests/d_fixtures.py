"""D 테스트 공용 준비물.

monsters 마스터 값이 아직 없어 테스트용 캐릭터를 만든다. code 는 't-' 로 시작해 실제 마스터와 구분한다.
"""

from datetime import date, timedelta
from itertools import count
from typing import Any

from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeRecommendation,
    DiseaseScope,
    Monster,
    MonsterState,
    RecommendationSourceType,
    UserAttackCycle,
    UserMonster,
)
from app.services.attack_cycles import CYCLE_POLICY_VERSION, cycle_end_for
from app.services.model_artifact import ModelArtifact, parse_artifact

_monster_no = count(1)

TEST_MODEL_VERSION = "test-model"


async def make_monster(
    factor_keys: list[str], *, code: str | None = None, scope: DiseaseScope = DiseaseScope.COMMON
) -> Monster:
    no = next(_monster_no)
    return await Monster.create(
        code=code or f"t-{no}", no=no, name=f"테스트{no}", factor_keys=factor_keys, disease_scope=scope
    )


async def make_target(
    user_id: int, factor_keys: list[str], *, impact: int = 80, scope: DiseaseScope = DiseaseScope.COMMON
) -> UserMonster:
    monster = await make_monster(factor_keys, scope=scope)
    return await UserMonster.create(
        user_id=user_id, monster_id=monster.id, impact_score=impact, state=MonsterState.RAGE
    )


async def make_cycle(
    user_id: int,
    factor_keys: list[str] | None = None,
    *,
    start: date | None = None,
    status: AttackCycleStatus = AttackCycleStatus.DRAFT,
) -> UserAttackCycle:
    target = await make_target(user_id, factor_keys or ["smoking_current", "physical_activity_low"])
    values: dict[str, Any] = {}
    if start is not None:
        status = AttackCycleStatus.ACTIVE if status == AttackCycleStatus.DRAFT else status
        values = {"start_date": start, "end_date": cycle_end_for(start)}
    return await UserAttackCycle.create(
        user_id=user_id,
        target_user_monster_id=target.id,
        status=status,
        policy_version=CYCLE_POLICY_VERSION,
        **values,
    )


async def make_card(
    user_id: int, challenge: Challenge, cycle: UserAttackCycle, rank: int = 1
) -> ChallengeRecommendation:
    return await ChallengeRecommendation.create(
        user_id=user_id,
        challenge_id=challenge.id,
        cycle_id=cycle.id,
        source_type=RecommendationSourceType.PREDICTION_PERSONAL,
        factor_key=challenge.factor_key or "bonus",
        rank=rank,
        recommended_at=cycle.created_at,
    )


def fake_artifact(
    global_scores: dict[str, dict[str, float]] | None = None,
    p95: dict[str, dict[str, float]] | None = None,
    *,
    model_version: str = TEST_MODEL_VERSION,
    status: str = "trained",
) -> ModelArtifact:
    """ai_worker/model_contract.py 형식의 가짜 아티팩트. 숫자는 테스트용이다."""
    diseases: dict[str, Any] = {}
    for disease in ("diabetes", "hypertension"):
        diseases[disease] = {
            "global_importance": [
                {"factor_key": key, "normalized_score": value, "importance": value / 1000, "rank": rank}
                for rank, (key, value) in enumerate((global_scores or {}).get(disease, {}).items(), 1)
            ],
            "positive_shap_p95_training_reference": {
                key: {"positive_shap_p95": value, "threat_eligible": True}
                for key, value in (p95 or {}).get(disease, {}).items()
            },
        }
    artifact = parse_artifact({"status": status, "model_version": model_version, "diseases": diseases})
    assert artifact is not None
    return artifact


def days_ago(today: date, days: int) -> date:
    return today - timedelta(days=days)
