import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeLog,
    ChallengeRecommendation,
    ContextType,
    Monster,
    OccurrenceStatus,
    RecommendationAction,
    Reward,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserChallengeStatus,
    UserMonster,
    UserReward,
    VerificationMethod,
    VerificationStatus,
    VerificationType,
)
from app.models.users import User
from app.repositories.user_repository import UserRepository
from app.services.attack_cycles import (
    EXTRA_FROM_DAY,
    MAX_ACTIVE_CHALLENGES,
    AttackCycleService,
    cycle_day,
    cycle_end_for,
    cycle_week,
    lock_user,
    today_kst,
)
from app.services.recommendations import target_monster_body

logger = logging.getLogger(__name__)

#: 첫 인정 완료 1회로 해금되는 보상. unlock_condition 은 자유 문장이라 코드로 판정하지 않고 여기 명시한다.
#: gluco_blade: '식후 걷기 인정 수행 1회 누적' · linked_challenge_code CH_WALK_AFTER_MEAL (reward-master.csv)
FIRST_COMPLETION_REWARD_CODES = ("gluco_blade",)

#: 시작할 수 있는 추천 카드 응답 상태. 아직 응답하지 않은 카드만 시작한다
STARTABLE_ACTIONS: tuple[RecommendationAction | None, ...] = (None,)
#: 미션을 시작할 수 있는 주기 상태
STARTABLE_CYCLE_STATUSES = (AttackCycleStatus.DRAFT, AttackCycleStatus.ACTIVE)


def week_start_for(value: date | datetime) -> date:
    """월요일 00:00 KST 기준 달력 주간의 시작일을 반환한다."""
    current = value.astimezone(config.TIMEZONE).date() if isinstance(value, datetime) else value
    return current - timedelta(days=current.weekday())


def progress_rate(completed_count: int, daily_target_count: int) -> float:
    """일일 목표 대비 진행률. 초과 수행은 100%에서 cap한다."""
    if daily_target_count <= 0:
        return 0.0
    capped = min(max(completed_count, 0), daily_target_count)
    return round(capped / daily_target_count * 100, 1)


def xp_for_completion(daily_xp: int, daily_target: int, completed_today: int) -> int:
    """인정 완료 1회의 XP (REQ-RECO-003 · 10/6 A·D 합의).

    하루 총 XP 를 개인 목표 횟수로 나눠 버림으로 지급하고, 나머지는 그날 목표 횟수를 채우는
    마지막 인정 완료에 더한다. 특정 슬롯 번호가 아니라 N번째 인정 완료 기준이다.
    """
    if daily_target <= 0 or completed_today > daily_target:
        return 0
    base, remainder = divmod(daily_xp, daily_target)
    return base + remainder if completed_today == daily_target else base


def plan_occurrences(challenge: Challenge, start: date, end: date) -> list[tuple[date, str, int]]:
    """예정 기회 (날짜, slot_code, sequence_no). 수행률 분모가 된다.

    식사 슬롯이 정해진 챌린지는 슬롯마다, 아니면 하루 목표 횟수만큼 독립 회차로 만든다.
    """
    slots = list(challenge.context_slots or [])
    if slots and len(slots) != challenge.daily_target_count:
        raise AppError(ErrorCode.VALIDATION_ERROR, message="하루 목표 횟수와 식사 슬롯 수가 맞지 않습니다.")
    planned: list[tuple[date, str, int]] = []
    day = start
    while day <= end:
        if slots:
            planned.extend((day, slot, 1) for slot in slots)
        else:
            planned.extend((day, "", seq) for seq in range(1, challenge.daily_target_count + 1))
        day += timedelta(days=1)
    return planned


@dataclass
class LogResult:
    log: ChallengeLog
    weekly_progress: int | None
    level_up: bool
    new_level: int | None
    #: 이번 기록으로 새로 지급한 보상. 이미 가진 보상이나 성향이 달라 주지 않은 경우는 None
    reward: Reward | None = None


class ChallengeCoreService:
    """챌린지 시작·수행·조회·중단 핵심 규칙."""

    def __init__(self) -> None:
        self.cycles = AttackCycleService()

    async def start_from_recommendations(
        self,
        *,
        user_id: int,
        recommendation_ids: list[int],
        safety_confirmed: bool | None = None,
        now: datetime | None = None,
    ) -> list[UserChallenge]:
        """CHLG-05. 첫 시작은 draft 주기를 active 로 바꾸고 D0·D28 을 함께 확정한다 (REQ-CHLG-002·011).

        1단계는 고정 원형까지다. 목표·난이도·XP 는 시작 시 마스터에서 복사한다.
        """
        if not 1 <= len(recommendation_ids) <= MAX_ACTIVE_CHALLENGES:
            raise AppError(ErrorCode.VALIDATION_ERROR)
        if len(set(recommendation_ids)) != len(recommendation_ids):
            raise AppError(ErrorCode.VALIDATION_ERROR)

        current = now or datetime.now(config.TIMEZONE)
        today = today_kst(current)
        await self.cycles.close_expired(user_id, today, current)

        created: list[UserChallenge] = []
        async with in_transaction():
            # 사용자 → 주기 → 추천 순으로 잠그고, 잠금을 얻은 뒤에 모든 조건을 검사한다
            await lock_user(user_id)
            cycle, ordered_recommendations = await self._lock_start_recommendations(user_id, recommendation_ids)
            ordered_challenges = await self._load_start_challenges(user_id, cycle, ordered_recommendations)
            if any(ch.safety_check_required for ch in ordered_challenges) and safety_confirmed is not True:
                raise AppError(ErrorCode.CHLG_SAFETY_CONFIRMATION_REQUIRED)

            active = UserChallenge.filter(user_id=user_id, status=UserChallengeStatus.ACTIVE)
            slots = self.cycles.remaining_slots(
                cycle,
                active_in_cycle=await active.filter(cycle_id=cycle.id).count(),
                active_total=await active.count(),
                today=today,
            )
            if len(ordered_challenges) > slots:
                raise AppError(ErrorCode.CHLG_LIMIT_EXCEEDED)

            if cycle.status == AttackCycleStatus.DRAFT:
                cycle.status = AttackCycleStatus.ACTIVE
                cycle.start_date = today
                cycle.end_date = cycle_end_for(today)
                await cycle.save(update_fields=["status", "start_date", "end_date", "updated_at"])
            elif (cycle_day(cycle, today) or 0) >= EXTRA_FROM_DAY:
                cycle.extra_added_count += len(ordered_challenges)
                await cycle.save(update_fields=["extra_added_count", "updated_at"])

            end_date = cycle.end_date
            if end_date is None:
                raise AppError(ErrorCode.INTERNAL_ERROR)
            for recommendation, challenge in zip(ordered_recommendations, ordered_challenges, strict=True):
                mission = await UserChallenge.create(
                    user_id=user_id,
                    challenge_id=challenge.id,
                    recommendation_id=recommendation.id,
                    source_prediction_id=None,
                    cycle_id=cycle.id,
                    status=UserChallengeStatus.ACTIVE,
                    start_date=today,
                    # 투입 시점과 관계없이 주기 공통 종료일. 초기 28일, D7 추가 21일
                    end_date=end_date,
                    daily_target_count_snapshot=challenge.daily_target_count,
                    target_value_snapshot=challenge.target_value,
                    duration_days_snapshot=(end_date - today).days + 1,
                    # 시작 시 하루 XP 를 고정한다. 진행 중 마스터가 바뀌어도 다시 계산하지 않는다
                    goal_config_snapshot={"difficulty": str(challenge.difficulty), "daily_xp": challenge.reward_xp},
                )
                await UserChallengeOccurrence.bulk_create(
                    [
                        UserChallengeOccurrence(
                            user_challenge_id=mission.id, scheduled_date=day, slot_code=slot, sequence_no=seq
                        )
                        for day, slot, seq in plan_occurrences(challenge, today, end_date)
                    ]
                )
                created.append(mission)
                recommendation.action = RecommendationAction.ACCEPTED
                recommendation.acted_at = current
                recommendation.consecutive_reject_count = 0
                await recommendation.save(update_fields=["action", "acted_at", "consecutive_reject_count"])
        return created

    async def _lock_start_recommendations(
        self, user_id: int, recommendation_ids: list[int]
    ) -> tuple[UserAttackCycle, list[ChallengeRecommendation]]:
        """현재 주기와 추천 카드를 잠그고 검증한다. 트랜잭션 안에서 부른다."""
        current_cycle = await self.cycles.get_current(user_id)
        if current_cycle is None:
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)
        cycle = await UserAttackCycle.select_for_update().get(id=current_cycle.id)
        if cycle.user_id != user_id or cycle.status not in STARTABLE_CYCLE_STATUSES:
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)

        recommendations = await ChallengeRecommendation.select_for_update().filter(
            id__in=recommendation_ids, user_id=user_id
        )
        if len(recommendations) != len(recommendation_ids):
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)
        by_id = {item.id: item for item in recommendations}
        ordered = [by_id[item_id] for item_id in recommendation_ids]

        # 지난 주기나 다른 주기의 추천으로 시작하지 않는다
        if any(item.cycle_id != cycle.id for item in ordered):
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)
        # 거절·해당없음·이미 시작한 카드로는 시작하지 않는다. 응답을 accepted 로 덮어쓰지 않는다
        if any(item.action not in STARTABLE_ACTIONS for item in ordered):
            raise AppError(ErrorCode.VALIDATION_ERROR, message="이미 응답한 추천 카드로는 시작할 수 없습니다.")
        # 1단계는 고정 원형만 시작한다. 개인 목표(proposed_goal) 반영은 후속 범위라
        # 개인 목표가 있는 카드를 마스터 목표로 바꿔 시작하지 않고 거부한다
        if any(item.proposed_goal is not None for item in ordered):
            raise AppError(ErrorCode.VALIDATION_ERROR, message="개인 목표가 있는 추천은 아직 시작할 수 없습니다.")
        return cycle, ordered

    async def _load_start_challenges(
        self, user_id: int, cycle: UserAttackCycle, recommendations: list[ChallengeRecommendation]
    ) -> list[Challenge]:
        """시작할 챌린지가 공략 대상과 연결되고 이미 진행 중이 아닌지 본다. 잠금 안에서 부른다."""
        challenge_ids = [item.challenge_id for item in recommendations]
        if len(set(challenge_ids)) != len(challenge_ids):
            raise AppError(ErrorCode.CHLG_ALREADY_ACTIVE)
        challenges = await Challenge.filter(id__in=challenge_ids, is_enabled=True)
        if len(challenges) != len(challenge_ids):
            raise AppError(ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND)
        challenge_by_id = {item.id: item for item in challenges}
        ordered = [challenge_by_id[item_id] for item_id in challenge_ids]

        monster = await self.cycles.target_monster(cycle)
        if any(challenge.factor_key not in monster.factor_keys for challenge in ordered):
            raise AppError(ErrorCode.VALIDATION_ERROR, message="이번 공략 대상과 연결되지 않은 챌린지입니다.")
        if any(challenge.context_type == ContextType.EVENT for challenge in ordered):
            # 예정 기회는 사용자가 확인한 이용일로만 만든다. 이용일을 받는 경로가 아직 없다
            raise AppError(ErrorCode.VALIDATION_ERROR, message="예정 이용일을 확인한 뒤에 시작할 수 있습니다.")
        if await UserChallenge.filter(
            user_id=user_id, challenge_id__in=challenge_ids, status=UserChallengeStatus.ACTIVE
        ).exists():
            raise AppError(ErrorCode.CHLG_ALREADY_ACTIVE)
        return ordered

    async def record_log(
        self,
        *,
        user_id: int,
        user_challenge_id: int,
        occurred_at: datetime,
        context_slot: str | None,
        value: Decimal | None,
        verification_method: VerificationMethod,
        evidence_url: str | None,
        now: datetime | None = None,
    ) -> LogResult:
        """CHLG-07. 공략 점수만 즉시 올리고 위협도는 건드리지 않는다 (REQ-CHLG-007).

        미션·기회 잠금, 조건부 완료 갱신, XP 지급을 한 트랜잭션에서 한다.
        """
        current = now or datetime.now(config.TIMEZONE)
        await self.cycles.close_expired(user_id, today_kst(current), current)

        async with in_transaction():
            mission, cycle = await self._active_mission(user_id, user_challenge_id)
            occurred = self._occurred_in_period(mission, occurred_at, current)
            log_date = occurred.date()
            challenge = await Challenge.get(id=mission.challenge_id)
            status = self._verify(challenge, mission, verification_method, value, evidence_url)
            self._check_slot(challenge, context_slot)

            same_day = ChallengeLog.filter(user_challenge_id=mission.id, log_date=log_date)
            if context_slot is not None and await same_day.filter(context_slot=context_slot).exists():
                raise AppError(ErrorCode.CHLG_LOG_DUPLICATED)

            occurrence = (
                await UserChallengeOccurrence.select_for_update()
                .filter(
                    user_challenge_id=mission.id,
                    scheduled_date=log_date,
                    slot_code=context_slot or "",
                    status=OccurrenceStatus.PLANNED,
                )
                .order_by("sequence_no")
                .first()
            )
            try:
                log = await ChallengeLog.create(
                    user_challenge_id=mission.id,
                    log_date=log_date,
                    occurred_at=occurred,
                    sequence_no=1 if context_slot else await same_day.count() + 1,
                    context_slot=context_slot,
                    value=value,
                    unit=challenge.unit if value is not None else None,
                    verification_method=verification_method,
                    verification_status=status,
                    evidence_url=evidence_url,
                    # 목표를 넘긴 수행은 저장하되 진행률과 보상에는 넣지 않는다 (REQ-CHLG-003)
                    reward_eligible=occurrence is not None,
                    xp_granted=0,
                )
            except IntegrityError as exc:
                # 같은 날 같은 슬롯이 동시에 들어오면 유니크 제약이 막는다
                raise AppError(ErrorCode.CHLG_LOG_DUPLICATED) from exc

            if occurrence is None or not await self._complete(occurrence, log, current):
                if log.reward_eligible:
                    log.reward_eligible = False
                    await log.save(update_fields=["reward_eligible"])
                return LogResult(log=log, weekly_progress=None, level_up=False, new_level=None)

            completed_today = await UserChallengeOccurrence.filter(
                user_challenge_id=mission.id, scheduled_date=log_date, status=OccurrenceStatus.COMPLETED
            ).count()
            xp = xp_for_completion(
                self._daily_xp(mission, challenge), mission.daily_target_count_snapshot, completed_today
            )
            level_up, new_level = False, None
            if xp > 0:
                level_up, new_level = await self._grant_xp(user_id, xp)
                log.xp_granted = xp
                await log.save(update_fields=["xp_granted"])
            reward = await self._grant_first_completion_rewards(user_id, challenge, current)

            updated = await self.add_weekly_progress(
                user_id=user_id,
                factor_key=challenge.factor_key,
                progress_value=challenge.progress_value,
                occurred_at=current,
            )
        target_id = cycle.target_user_monster_id if cycle else None
        progress = next((item.weekly_progress for item in updated if item.id == target_id), None)
        if progress is None and updated:
            progress = updated[0].weekly_progress
        return LogResult(log=log, weekly_progress=progress, level_up=level_up, new_level=new_level, reward=reward)

    @staticmethod
    async def _complete(occurrence: UserChallengeOccurrence, log: ChallengeLog, now: datetime) -> bool:
        """planned 일 때만 completed 로 바꾼다. 다른 요청이 먼저 완료했으면 False."""
        changed = await UserChallengeOccurrence.filter(id=occurrence.id, status=OccurrenceStatus.PLANNED).update(
            status=OccurrenceStatus.COMPLETED, completed_log_id=log.id, completed_at=now
        )
        return changed == 1

    @staticmethod
    async def _active_mission(user_id: int, user_challenge_id: int) -> tuple[UserChallenge, UserAttackCycle | None]:
        """미션과 주기를 잠그고 진행 중인지 다시 본다. 트랜잭션 안에서 부른다."""
        mission = await UserChallenge.select_for_update().get_or_none(id=user_challenge_id, user_id=user_id)
        if mission is None:
            raise AppError(ErrorCode.CHLG_NOT_FOUND)
        if mission.status != UserChallengeStatus.ACTIVE:
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
        if mission.cycle_id is None:
            return mission, None
        cycle = await UserAttackCycle.select_for_update().get_or_none(id=mission.cycle_id)
        if cycle is None or cycle.status != AttackCycleStatus.ACTIVE:
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
        return mission, cycle

    @staticmethod
    def _occurred_in_period(mission: UserChallenge, occurred_at: datetime, now: datetime) -> datetime:
        """수행 시각을 KST 로 맞추고 미션 기간 안인지 본다. log_date 는 KST 달력 날짜다."""
        occurred = (occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=config.TIMEZONE)).astimezone(
            config.TIMEZONE
        )
        if occurred > now:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="아직 오지 않은 시각은 기록할 수 없습니다.")
        if occurred.date() > mission.end_date:
            # 종료 이후 기록·보상은 막는다 (REQ-CHLG-011)
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
        if occurred.date() < mission.start_date:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="챌린지 시작 전 날짜는 기록할 수 없습니다.")
        return occurred

    @staticmethod
    def _check_slot(challenge: Challenge, context_slot: str | None) -> None:
        slots = list(challenge.context_slots or [])
        if slots and context_slot not in slots:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="선택한 식사 슬롯이 아닙니다.")
        if not slots and context_slot is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, message="슬롯이 없는 챌린지입니다.")

    def _verify(
        self,
        challenge: Challenge,
        mission: UserChallenge,
        method: VerificationMethod,
        value: Decimal | None,
        evidence_url: str | None,
    ) -> VerificationStatus:
        """인증 방식은 챌린지당 하나. 수동 대체는 허용된 챌린지만 (REQ-CHLG-008)."""
        if method == VerificationMethod.MANUAL_FALLBACK:
            if not challenge.manual_fallback_allowed:
                raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
            return VerificationStatus.SELF_CONFIRMED
        if str(method) != str(challenge.verification_type):
            raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)

        if challenge.verification_type == VerificationType.MANUAL:
            return VerificationStatus.SELF_CONFIRMED
        if challenge.verification_type == VerificationType.TIMER:
            # 회차별로 목표 이상이어야 한다. 부족분을 다른 회차로 환산하지 않는다
            target = mission.target_value_snapshot
            if value is None or (target is not None and value < target):
                raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
            return VerificationStatus.PASS
        if challenge.verification_type == VerificationType.PHOTO:
            # AI 판별 없이 업로드 여부만 본다
            if not evidence_url:
                raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED)
            return VerificationStatus.PASS
        # value·time·system 은 1단계 후보에 없고 완료 판정 규칙이 승인되지 않았다
        raise AppError(ErrorCode.CHLG_VERIFICATION_FAILED, message="아직 지원하지 않는 인증 방식입니다.")

    @staticmethod
    def _daily_xp(mission: UserChallenge, challenge: Challenge) -> int:
        snapshot = mission.goal_config_snapshot or {}
        daily_xp = snapshot.get("daily_xp")
        if isinstance(daily_xp, int):
            return daily_xp
        # goal_config_snapshot 이 없는 레거시 행만 마스터 값으로 되돌아간다
        return challenge.reward_xp

    @staticmethod
    async def _grant_first_completion_rewards(user_id: int, challenge: Challenge, now: datetime) -> Reward | None:
        """연결된 챌린지를 인정 완료하면 보상을 준다. 두 번째부터는 (user_id, reward_id) 유니크로 조용히 넘어간다.

        보상은 인증의 부산물이라 여기서 문제가 생겨도 인증은 성공해야 한다.
        중첩 트랜잭션(SAVEPOINT)으로 보상 쓰기만 되돌리고 바깥 인증 트랜잭션은 그대로 둔다.
        이번에 새로 만든 보상만 돌려준다. 거짓 획득 안내를 만들지 않도록 A·D 가 합의했다.
        """
        granted: Reward | None = None
        try:
            async with in_transaction():
                rewards = await Reward.filter(
                    code__in=FIRST_COMPLETION_REWARD_CODES, linked_challenge_code=challenge.code, is_enabled=True
                )
                if not rewards:
                    return None
                user = await User.get(id=user_id)
                for reward in rewards:
                    # REQ-RECO-001 은 사용자가 고른 보상 유형에 맞는 보상을 준다고 한다.
                    # 1단계 보상 마스터는 성장형(grow) 아이템 하나뿐이라, 다른 유형을 고른 사용자에게는 주지 않는다.
                    # D 의 1단계 보상 범위 문서를 읽고 A 가 정한 해석이다. 지급하지 않았을 때는 응답에도 남기지 않는다.
                    if str(reward.motivation_type) != str(user.motivation_type):
                        continue
                    _, created = await UserReward.get_or_create(
                        user_id=user_id, reward_id=reward.id, defaults={"acquired_at": now}
                    )
                    if created and granted is None:
                        granted = reward
        except Exception:
            # SAVEPOINT 가 되돌려졌으므로 지급하지 않은 것으로 본다
            logger.exception("보상 지급 실패 · user_id=%s challenge=%s", user_id, challenge.code)
            return None
        return granted

    @staticmethod
    async def _grant_xp(user_id: int, amount: int) -> tuple[bool, int | None]:
        """경험치는 A 의 grant_xp() 로 요청한다. 레벨 판정도 A 쪽 결과를 그대로 쓴다."""
        result = await UserRepository().grant_xp(user_id, amount)
        if result is None:
            return False, None
        return result.level_up, result.new_level

    async def list_user_challenges(
        self, *, user_id: int, status: UserChallengeStatus, page: int, size: int, now: datetime | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """CHLG-06. 진행률은 인정 완료 기회 ÷ 예정 기회이고 공략 점수와 별개다."""
        current = now or datetime.now(config.TIMEZONE)
        today = today_kst(current)
        await self.cycles.close_expired(user_id, today, current)

        query = UserChallenge.filter(user_id=user_id, status=status)
        total = await query.count()
        missions = await query.order_by("-start_date", "-id").offset((page - 1) * size).limit(size)
        challenges = {item.id: item for item in await Challenge.filter(id__in=[m.challenge_id for m in missions])}
        cycles = {
            item.id: item
            for item in await UserAttackCycle.filter(id__in=[m.cycle_id for m in missions if m.cycle_id is not None])
        }
        targets: dict[int, dict[str, Any]] = {}
        for linked in cycles.values():
            targets[linked.id] = target_monster_body(await self.cycles.target_monster(linked))

        items = []
        for mission in missions:
            challenge = challenges[mission.challenge_id]
            cycle = cycles.get(mission.cycle_id) if mission.cycle_id else None
            occurrences = UserChallengeOccurrence.filter(user_challenge_id=mission.id)
            scheduled = await occurrences.count()
            completed = await occurrences.filter(status=OccurrenceStatus.COMPLETED).count()
            snapshot = mission.goal_config_snapshot or {}
            items.append(
                {
                    "user_challenge_id": mission.id,
                    "challenge_id": challenge.id,
                    "title": challenge.title,
                    "factor_key": challenge.factor_key,
                    "difficulty": snapshot.get("difficulty", str(challenge.difficulty)),
                    "verification_type": challenge.verification_type,
                    "context_type": challenge.context_type,
                    "context_label": challenge.context_label,
                    "cycle_id": mission.cycle_id,
                    "cycle_week": cycle_week(cycle, today) if cycle else None,
                    "target_monster": targets.get(cycle.id) if cycle else None,
                    "start_date": mission.start_date,
                    "end_date": mission.end_date,
                    "completed_count": completed,
                    "daily_target_count": mission.daily_target_count_snapshot,
                    "target_value": float(mission.target_value_snapshot)
                    if mission.target_value_snapshot is not None
                    else None,
                    "goal_config_snapshot": mission.goal_config_snapshot,
                    "scheduled_opportunity_count": scheduled,
                    "progress_rate": round(completed / scheduled, 4) if scheduled else None,
                    "habit_established": mission.habit_established,
                }
            )
        return items, total

    async def list_logs(
        self,
        *,
        user_id: int,
        user_challenge_id: int,
        start_date: date | None,
        end_date: date | None,
        page: int,
        size: int,
    ) -> tuple[list[ChallengeLog], int]:
        """CHLG-08. 본인 미션의 기록만."""
        if not await UserChallenge.filter(id=user_challenge_id, user_id=user_id).exists():
            raise AppError(ErrorCode.CHLG_NOT_FOUND)
        query = ChallengeLog.filter(user_challenge_id=user_challenge_id)
        if start_date is not None:
            query = query.filter(log_date__gte=start_date)
        if end_date is not None:
            query = query.filter(log_date__lte=end_date)
        total = await query.count()
        logs = await query.order_by("-log_date", "-occurred_at", "-id").offset((page - 1) * size).limit(size)
        return logs, total

    async def stop(
        self,
        *,
        user_id: int,
        user_challenge_id: int,
        stop_reason: str | None = None,
        now: datetime | None = None,
    ) -> UserChallenge:
        item = await UserChallenge.get_or_none(id=user_challenge_id, user_id=user_id)
        if item is None:
            raise AppError(ErrorCode.CHLG_NOT_FOUND)
        if item.status != UserChallengeStatus.ACTIVE:
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
        item.status = UserChallengeStatus.ABANDONED
        item.stopped_at = now or datetime.now(config.TIMEZONE)

        update_fields = ["status", "stopped_at", "updated_at"]

        if stop_reason is not None:
            item.stop_reason = stop_reason
            update_fields.append("stop_reason")

        await item.save(update_fields=update_fields)
        return item

    async def add_weekly_progress(
        self,
        *,
        user_id: int,
        factor_key: str | None,
        progress_value: int,
        occurred_at: datetime | None = None,
    ) -> list[UserMonster]:
        """REQ-CHLG-007: 수행 성공 시 공략 점수만 올린다."""
        if factor_key is None or progress_value <= 0:
            return []
        current = occurred_at or datetime.now(config.TIMEZONE)
        week_start = week_start_for(current)
        monsters = await Monster.filter(is_enabled=True).all()
        matched = [monster for monster in monsters if factor_key in monster.factor_keys]
        updated: list[UserMonster] = []
        for monster in matched:
            user_monster, _ = await UserMonster.get_or_create(user_id=user_id, monster_id=monster.id)
            if user_monster.progress_week_start != week_start:
                user_monster.weekly_progress = 0
                user_monster.progress_week_start = week_start
            user_monster.weekly_progress = min(
                100,
                user_monster.weekly_progress + progress_value,
            )
            await user_monster.save(update_fields=["weekly_progress", "progress_week_start", "updated_at"])
            updated.append(user_monster)
        return updated
