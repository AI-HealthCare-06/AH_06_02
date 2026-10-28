"""몬스터 기준 데이터 코호트. 한 사용자의 기록을 캐릭터(비세라·알데·코티니·스파이크)별로 묶는다.

챗봇이 컨텍스트로 쓰는 값은 llm_context 만이다. 건강 수치·확률·진단 여부는 LLM 에 보내지 않고
캐릭터 상태·챌린지 단계·수행률 구간처럼 서버가 이미 화면에 보여 주는 범주만 넘긴다.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.challenges import Challenge, Monster, UserChallenge, UserChallengeStatus, UserMonster
from app.models.health_records import HealthRecord, InputMode
from app.models.predictions import Prediction, PredictionStatus
from app.services.attack_cycles import AttackCycleService
from app.services.challenge_goals import KEEP_AT, RAISE_AT, goal_policy, mission_level

#: 코호트마다 들고 있을 최근 건강기록·예측 수
RECENT_LIMIT = 5


@dataclass(frozen=True)
class MissionHistory:
    user_challenge_id: int
    challenge_code: str
    cycle_id: int | None
    status: str
    start_date: Any
    end_date: Any
    level: int | None
    completion_rate: Decimal | None


@dataclass
class MonsterCohort:
    monster_code: str
    monster_name: str
    factor_keys: list[str]
    state: str | None = None
    impact_score: int | None = None
    is_target: bool = False
    health_record_ids: list[int] = field(default_factory=list)
    prediction_ids: list[int] = field(default_factory=list)
    #: 진행 중 미션 (수행 이력)
    active: list[MissionHistory] = field(default_factory=list)
    #: 끝난 미션 (챌린지 이력). 최근 것부터
    finished: list[MissionHistory] = field(default_factory=list)


def completion_band(rate: Decimal | None) -> str:
    """수행률을 순환 규칙의 구간으로만 알린다. 정확한 값은 LLM 에 넘기지 않는다."""
    if rate is None:
        return "none"
    if rate >= RAISE_AT:
        return "high"
    if rate >= KEEP_AT:
        return "middle"
    return "low"


class MonsterCohortService:
    async def build(self, user_id: int) -> dict[str, MonsterCohort]:
        monsters = await Monster.filter(is_enabled=True).order_by("no")
        owned = {item.monster_id: item for item in await UserMonster.filter(user_id=user_id)}
        cycle = await AttackCycleService().get_current(user_id)
        records = [
            row.id
            for row in await HealthRecord.filter(user_id=user_id)
            .exclude(input_mode=InputMode.DAILY)
            .order_by("-recorded_at", "-id")
            .limit(RECENT_LIMIT)
        ]
        predictions = [
            row.id
            for row in await Prediction.filter(user_id=user_id, status=PredictionStatus.DONE)
            .order_by("-predicted_at", "-id")
            .limit(RECENT_LIMIT)
        ]
        missions = await UserChallenge.filter(user_id=user_id).order_by("-start_date", "-id")
        challenges = {item.id: item for item in await Challenge.filter(id__in=[m.challenge_id for m in missions])}

        cohorts: dict[str, MonsterCohort] = {}
        for monster in monsters:
            mine = owned.get(monster.id)
            cohort = MonsterCohort(
                monster_code=monster.code,
                monster_name=monster.name,
                factor_keys=list(monster.factor_keys or []),
                state=str(mine.state) if mine else None,
                impact_score=mine.impact_score if mine else None,
                is_target=bool(cycle and mine and cycle.target_user_monster_id == mine.id),
                # 예측·기록은 모든 캐릭터가 같은 입력을 공유한다. 캐릭터에 반영된 기록이 있으면 그것부터 둔다
                health_record_ids=_first(mine.last_health_record_id if mine else None, records),
                prediction_ids=_first(mine.last_prediction_id if mine else None, predictions),
            )
            for mission in missions:
                challenge = challenges.get(mission.challenge_id)
                if challenge is None or challenge.factor_key not in cohort.factor_keys:
                    continue
                history = _history(mission, challenge)
                (cohort.active if mission.status == UserChallengeStatus.ACTIVE else cohort.finished).append(history)
            cohorts[monster.code] = cohort
        return cohorts

    @staticmethod
    def llm_context(cohort: MonsterCohort) -> dict[str, Any]:
        """LLM 에 넘기는 범주 요약. 수치·확률·진단·날짜·ID 는 넣지 않는다."""
        return {
            "monster": cohort.monster_code,
            "state": cohort.state,
            "is_target": cohort.is_target,
            "active": [{"challenge_code": m.challenge_code, "level": m.level} for m in cohort.active],
            "history": [
                {
                    "challenge_code": m.challenge_code,
                    "level": m.level,
                    "completion": completion_band(m.completion_rate),
                }
                for m in cohort.finished[:RECENT_LIMIT]
            ],
        }


def _first(preferred: int | None, ids: list[int]) -> list[int]:
    if preferred is None:
        return list(ids)
    return [preferred, *[item for item in ids if item != preferred]][:RECENT_LIMIT]


def _history(mission: UserChallenge, challenge: Challenge) -> MissionHistory:
    policy = goal_policy(challenge)
    return MissionHistory(
        user_challenge_id=mission.id,
        challenge_code=challenge.code,
        cycle_id=mission.cycle_id,
        status=str(mission.status),
        start_date=mission.start_date,
        end_date=mission.end_date,
        level=mission_level(mission, challenge, policy) if policy else None,
        completion_rate=mission.completion_rate,
    )
