"""승인 카드 기반 추천 내부 연결. 공개 API·운영 코퍼스 승인은 별도로 확정한다."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Literal

import httpx
from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    Challenge,
    ChallengeRecommendation,
    UserChallenge,
    UserChallengeStatus,
)
from app.models.health_records import HealthRecord, InputMode
from app.models.users import User
from app.services.attack_cycles import lock_user, today_kst
from app.services.rag_cards import EvidenceCard, SituationAnswers, questions_for, search_cards, validate_selection
from app.services.rag_provider import SelectionProvider
from app.services.recommendations import GeneratedRecommendations, RecommendationService, phase1_candidates


@dataclass
class ConversationResult:
    mode: Literal["conversation", "rules", "ask", "hold"]
    recommendations: GeneratedRecommendations
    questions: list[dict[str, str]]
    reasons: dict[int, str]


#: 질문 문구가 전제하는 마스터 목표(목표값·하루 횟수·슬롯·인증 방식). 마스터가 바뀌면 질문과 함께 고친다
FIXED_GOALS: dict[str, tuple[Decimal | None, int, list[str] | None, str]] = {
    "CH_WALK_AFTER_MEAL": (Decimal("10"), 2, ["lunch", "dinner"], "timer"),
    "CH_WALK_ONE_STOP": (None, 1, None, "manual"),
    "CH_STAND_HOURLY": (Decimal("3"), 3, None, "timer"),
    "CH_STAIRS": (None, 1, None, "manual"),
    "CH_STRENGTH_10": (Decimal("10"), 1, None, "timer"),
    "CH_NO_DRINK_TODAY": (None, 1, None, "manual"),
    "CH_NO_SMOKE_TODAY": (None, 1, None, "manual"),
    "CH_WALK_EVENING_20": (Decimal("20"), 1, None, "timer"),
    "CH_HOUSEWORK_15": (Decimal("15"), 1, None, "timer"),
    "CH_SQUAT_15": (Decimal("15"), 1, None, "manual"),
    "CH_WALL_PUSHUP_10": (Decimal("10"), 1, None, "manual"),
    "CH_STAND_CALL": (None, 1, None, "manual"),
    "CH_SCREEN_BREAK": (None, 1, None, "manual"),
    "CH_WATER_NOT_SWEET": (None, 1, None, "manual"),
    "CH_NO_LATE_SNACK": (None, 1, None, "manual"),
    "CH_NO_ALCOHOL_AT_HOME": (None, 1, None, "manual"),
    "CH_ALCOHOL_FREE_DRINK": (None, 1, None, "manual"),
    "CH_POSTPONE_DRINKS": (None, 1, None, "manual"),
    "CH_DELAY_FIRST_CIG": (None, 1, None, "manual"),
    "CH_SMOKE_FREE_HOME": (None, 1, None, "manual"),
    "CH_QUIT_REASON": (None, 1, None, "manual"),
}


class ConversationRecommendationService:
    @staticmethod
    def _matches_fixed_contract(challenge: Challenge) -> bool:
        expected = FIXED_GOALS.get(challenge.code)
        return (
            expected is None
            or (
                challenge.target_value,
                challenge.daily_target_count,
                challenge.context_slots,
                challenge.verification_type,
            )
            == expected
        )

    def __init__(
        self,
        rules: RecommendationService,
        cards: list[EvidenceCard],
        provider: SelectionProvider | None = None,
        *,
        enabled: bool = False,
    ) -> None:
        self.rules, self.cards, self.provider, self.enabled = rules, cards, provider, enabled

    @staticmethod
    async def _record_id(user_id: int) -> int | None:
        row = (
            await HealthRecord.filter(user_id=user_id)
            .exclude(input_mode=InputMode.DAILY)
            .order_by("-recorded_at", "-id")
            .first()
        )
        return row.id if row else None

    async def personalize(
        self,
        user: User,
        generated: GeneratedRecommendations,
        *,
        query: str,
        answers: SituationAnswers,
        asked: list[str],
    ) -> ConversationResult:
        """서버가 생성한 규칙 후보만 개인화한다. 클라이언트가 모델 점수·대상을 공급하지 않는다."""
        if any(row.user_id != user.id for row in generated.items) or generated.cycle.user_id != user.id:
            raise AppError(ErrorCode.FORBIDDEN)
        if not self.enabled or self.provider is None:
            return ConversationResult("rules", generated, [], {})
        if any(not self._matches_fixed_contract(generated.challenges[row.challenge_id]) for row in generated.items):
            return ConversationResult("hold", replace(generated, items=[]), [], {})
        codes = {generated.challenges[row.challenge_id].code for row in generated.items}
        questions = questions_for(codes, answers, asked)
        if answers.activity_limited:
            return ConversationResult("hold", replace(generated, items=[]), [], {})
        if questions:
            return ConversationResult("ask", replace(generated, items=[]), questions, {})
        retrieved = search_cards(self.cards, query, codes, answers)
        if not retrieved:
            return ConversationResult("rules", generated, [], {})
        if not self.provider.model_version or len(self.provider.model_version) > 32:
            raise ValueError("모델 식별자는 1~32자여야 합니다.")
        record_id = await self._record_id(user.id)
        selected = None
        try:
            selected = validate_selection(await self.provider.select(retrieved, answers), retrieved, codes, answers)
        except (ValueError, AppError, OSError, TimeoutError, httpx.HTTPError):
            # 모델 실패 내용·개인 대화·토큰을 로그에 남기지 않는다.
            selected = None
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "answers": answers.model_dump(),
                    "cycle_id": generated.cycle.id,
                    "record_id": record_id,
                    "model_version": generated.model_version,
                    "provider": self.provider.model_version,
                    "cards": [(card.card_id, card.version) for card in retrieved],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return await self._commit(
            user, generated, record_id, selected, fingerprint, retrieved, answers, asked, self.provider.model_version
        )

    async def _commit(
        self,
        user: User,
        generated: GeneratedRecommendations,
        record_id: int | None,
        selected: list[tuple[str, EvidenceCard]] | None,
        fingerprint: str,
        retrieved: list[EvidenceCard],
        answers: SituationAnswers,
        asked: list[str],
        model_version: str,
    ) -> ConversationResult:
        """외부 호출 이후 사용자 잠금 안에서 다시 검증하고 원자적으로 저장한다."""
        async with in_transaction():
            await lock_user(user.id)
            cycle = await self.rules.cycles.get_current(user.id)
            artifact = self.rules.artifact_source()
            rows = await ChallengeRecommendation.select_for_update().filter(
                id__in=[row.id for row in generated.items], user_id=user.id
            )
            active = UserChallenge.filter(user_id=user.id, status=UserChallengeStatus.ACTIVE)
            if (
                cycle is None
                or cycle.id != generated.cycle.id
                or artifact is None
                or artifact.model_version != generated.model_version
                or (cycle.end_date is not None and cycle.end_date < today_kst())
                or cycle.target_user_monster_id != generated.cycle.target_user_monster_id
                or await self._record_id(user.id) != record_id
                or len(rows) != len(generated.items)
                or any(row.cycle_id != cycle.id for row in rows)
                or any(row.action is not None for row in rows)
                or self.rules.cycles.remaining_slots(
                    cycle, await active.filter(cycle_id=cycle.id).count(), await active.count(), today_kst()
                )
                <= 0
            ):
                return ConversationResult("hold", replace(generated, items=[]), [], {})
            blocked = await self.rules._blocked_challenge_ids(user.id, datetime.now(config.TIMEZONE))
            candidates = {card.id: card for card in await phase1_candidates()}
            monster = await self.rules.cycles.target_monster(cycle)
            scores, _ = await self.rules._factor_scores(user, monster, artifact)
            if any(
                row.challenge_id not in candidates
                or row.challenge_id in blocked
                or candidates[row.challenge_id].factor_key not in monster.factor_keys
                or row.factor_key != candidates[row.challenge_id].factor_key
                or candidates[row.challenge_id].target_value != generated.challenges[row.challenge_id].target_value
                or candidates[row.challenge_id].daily_target_count
                != generated.challenges[row.challenge_id].daily_target_count
                or candidates[row.challenge_id].context_slots != generated.challenges[row.challenge_id].context_slots
                or candidates[row.challenge_id].verification_type
                != generated.challenges[row.challenge_id].verification_type
                or row.factor_key not in scores
                or scores[row.factor_key].score <= 0
                for row in rows
            ):
                return ConversationResult("hold", replace(generated, items=[]), [], {})
            by_code = {candidates[row.challenge_id].code: row for row in rows}
            existing = [row for row in rows if (row.conversation_snapshot or {}).get("fingerprint")]
            if existing:
                if any((row.conversation_snapshot or {}).get("fingerprint") != fingerprint for row in existing):
                    return ConversationResult("hold", replace(generated, items=[]), [], {})
                existing.sort(key=lambda row: row.rank)
                evidence_by_id = {card.card_id: card for card in retrieved}
                if any(not row.evidence_card_ids or row.evidence_card_ids[0] not in evidence_by_id for row in existing):
                    return ConversationResult("hold", replace(generated, items=[]), [], {})
                return ConversationResult(
                    "conversation",
                    replace(generated, items=existing),
                    [],
                    {row.id: evidence_by_id[(row.evidence_card_ids or [""])[0]].guidance for row in existing},
                )
            if not selected:
                return ConversationResult("rules", generated, [], {})
            output = []
            reasons = {}
            for code, evidence in selected:
                row = by_code[code]
                output.append(row)
                reasons[row.id] = evidence.guidance
            # 앞선 모든 검증이 통과한 뒤에만 쓰므로 잘못된 한 항목이 앞 항목을 저장하지 않는다.
            for rank, ((_, evidence), row) in enumerate(zip(selected, output, strict=True), 1):
                # 기존 규칙·예측 후보를 대화로 골라도 후보를 만든 원래 출처는 유지한다.
                row.rank = rank
                row.factor_score = Decimal(str(round(scores[row.factor_key].score, 5)))
                row.conversation_snapshot = {
                    "policy_version": "RAG-FIXED-20261012-v1",
                    "fingerprint": fingerprint,
                    "answers": answers.model_dump(),
                    "asked": asked,
                    "card_versions": {evidence.card_id: evidence.version},
                    "model_version": artifact.model_version,
                    "health_record_id": record_id,
                }
                row.llm_model_version = model_version
                row.evidence_card_ids = [evidence.card_id]
                # 현재 시작 계약은 고정 원형만 지원한다. 개인 목표로 저장하지 않는다.
                row.proposed_goal = None
                await row.save(
                    update_fields=[
                        "rank",
                        "factor_score",
                        "conversation_snapshot",
                        "llm_model_version",
                        "evidence_card_ids",
                        "proposed_goal",
                    ]
                )
            return ConversationResult("conversation", replace(generated, items=output), [], reasons)
