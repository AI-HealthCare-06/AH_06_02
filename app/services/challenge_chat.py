"""질의 챗봇. 답은 선택지를 눌러서만 받는다(자유 입력 없음).

열린 요인에 맞는 질문 의도를 고르고, 생성된 질문과 선택지의 의미 및 값을 검사한다.
운동 범위와 수행 가능 답으로 남은 챌린지만 후보가 되고 판단 모델은 후보 라벨의 확률을 낸다.
이유 문장은 답한 질문 페이지에서, 근거 카드는 승인 카드에서 가져온다. 목표 값은 주기 규칙이 채운다.

건강 수치·확률·진단 여부·이름은 보내지 않는다. 생성이나 검토가 실패하면 고정 질문을 쓴다.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

import httpx
from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeRecommendation,
    UserAttackCycle,
    UserChallenge,
    UserChallengeStatus,
)
from app.models.health_records import HealthRecord, InputMode
from app.models.users import User
from app.services.attack_cycles import lock_user, today_kst
from app.services.challenge_goals import display_goal
from app.services.challenge_selections import (
    CLAIM_PATTERN,
    ValidatedSelection,
    candidate_labels,
    goal_numbers,
    rank_selections,
    validate_judgment,
)
from app.services.conversation_recommendations import ConversationRecommendationService
from app.services.monster_cohorts import MonsterCohortService
from app.services.page_index import PageIndex
from app.services.rag_cards import (
    ANSWER_FIELDS,
    CODE_BY_ANSWER_KEY,
    SUPPORTED_CODES,
    ActivityAnswers,
    EvidenceCard,
    QuestionPage,
    SituationAnswers,
    activity_range_allows,
    classify_activity_range,
)
from app.services.rag_provider import ChatProvider, failure_label
from app.services.recommendations import EligibleChallenges, GeneratedRecommendations, RecommendationService

logger = logging.getLogger(__name__)

CHAT_POLICY_VERSION = "RAG-CHAT-20261102-v5"
#: 선택 단계에 넘길 근거 카드 수. 후보마다 한 장은 먼저 넣는다
MAX_CONTEXT_CARDS = 12
QUESTION_PREFIXES = ("", "잠깐 여쭤볼게요. ", "한 가지만 더 확인할게요. ", "이번에는 이렇게 여쭤볼게요. ")
ANSWER_LABEL_VARIANTS = {"yes": {"가능해요"}, "no": {"지금은 어려워요"}}
PERIOD_WORDS = ("오늘", "내일", "모레", "이번 주", "다음 주", "매일", "매주", "이번 달", "다음 달")

ChatMode = Literal["conversation", "rules", "ask", "hold"]

FALLBACK_ANSWERS: dict[str, str] = {
    "conversation": "답해 주신 내용에 맞춰 챌린지를 골랐어요.",
    "rules": "지금 받은 추천을 그대로 보여 드릴게요.",
    "ask": "하나만 골라 주세요.",
    "hold": "지금은 새 추천을 잠시 미룰게요. 진행 중인 챌린지를 무리 없이 이어가 주세요.",
}


@dataclass
class ChatResult:
    mode: ChatMode
    answer: str
    recommendations: GeneratedRecommendations
    questions: list[dict[str, Any]]
    reasons: dict[int, str]
    sources: list[str]


class ChallengeChatService:
    def __init__(
        self,
        rules: RecommendationService,
        index: PageIndex,
        provider: ChatProvider | None = None,
        *,
        enabled: bool = False,
        cohorts: MonsterCohortService | None = None,
    ) -> None:
        self.rules, self.index, self.provider, self.enabled = rules, index, provider, enabled
        self.cohorts = cohorts or MonsterCohortService()
        cards = [page.card for page in index.pages if page.card is not None]
        # 건강기록 확인·고정 계약 확인은 대화형 추천과 같은 코드를 쓴다
        self.conversation = ConversationRecommendationService(rules, cards)

    async def initial_entry(self, user: User) -> bool:
        """첫 검사 뒤 아직 추천이나 시작한 주기가 없는 사용자인지 확인한다."""
        if await UserAttackCycle.filter(user_id=user.id).exclude(status=AttackCycleStatus.DRAFT).exists():
            return False
        if await ChallengeRecommendation.filter(user_id=user.id).exists():
            return False
        return await HealthRecord.filter(user_id=user.id).exclude(input_mode=InputMode.DAILY).count() == 1

    async def select(
        self, user: User, answers: SituationAnswers, asked: list[str], activity: ActivityAnswers | None = None
    ) -> ChatResult:
        now = datetime.now(config.TIMEZONE)
        if activity is None and (not self.enabled or self.provider is None):
            return self._result("rules", await self.current_batch(user))
        found = await self.rules.eligible(user, now)
        activity_level = None
        question_count = len(asked)
        if activity is not None:
            activity_values = activity.model_dump(exclude={"clarifications"})
            question_count += sum(value not in {"unknown", "unsure"} for value in activity_values.values())
            question_count += activity.clarifications
            if question_count > 5:
                raise ValueError("질문은 최대 다섯 개까지 답할 수 있습니다.")
            activity_question = activity_assessment_question(activity)
            if activity_question is not None:
                if question_count >= 5 or ("unsure" in activity_values.values() and activity.clarifications >= 2):
                    return self._result("hold", found.batch([]))
                return self._result("ask", found.batch([]), questions=[activity_question])
            activity_level = classify_activity_range(activity_values)
            if activity_level is None:
                return self._result("hold", found.batch([]))
            activity_level = await self._activity_level(activity, activity_level)
        feasible = self._feasible(found)
        if activity is not None:
            feasible = {code: item for code, item in feasible.items() if activity_range_allows(code, activity_level)}
        if answers.activity_limited:
            return self._result("hold", found.batch([]))
        clear = activity is not None and question_count >= 3 and any(answers.supports(code) for code in feasible)
        question = (
            self.index.next_question(set(feasible), answers, asked, f"{user.id}:{found.cycle.id}")
            if question_count < 5 and not clear
            else None
        )
        if question is not None:
            question = await self._choose_question(question, set(feasible), answers, asked)
            return self._result("ask", found.batch([]), questions=[await self._question(question, answers)])
        return await self._select_candidates(user, found, answers, asked, activity, activity_level, feasible, now)

    async def _activity_level(self, activity: ActivityAnswers, confirmed: int) -> int:
        """모델의 운동 범위는 사용자가 확인한 상한을 넘지 않는다."""
        classify = getattr(self.provider, "classify_activity", None) if self.enabled else None
        if classify is None:
            return confirmed
        try:
            result = await classify(activity.model_dump(exclude={"clarifications"}))
            level = result.get("level") if isinstance(result, dict) else None
            if type(level) is not int or level not in {1, 2, 3}:
                raise ValueError("운동 범위 응답이 올바르지 않습니다.")
            return min(confirmed, level)
        except (ValueError, TypeError, AppError, OSError, TimeoutError, httpx.HTTPError) as exc:
            logger.warning("운동 범위 판단 호출·검증 실패, 확인된 답을 쓴다: %s", failure_label(exc))
            return confirmed

    async def _select_candidates(
        self,
        user: User,
        found: EligibleChallenges,
        answers: SituationAnswers,
        asked: list[str],
        activity: ActivityAnswers | None,
        activity_level: int | None,
        feasible: dict[str, Challenge],
        now: datetime,
    ) -> ChatResult:
        selectable = {code: challenge for code, challenge in feasible.items() if answers.supports(code)}

        cards = self._context_cards(selectable)
        selectable = {
            code: challenge for code, challenge in selectable.items() if any(c.challenge_code == code for c in cards)
        }
        if not selectable:
            if activity is not None:
                return self._result("hold", found.batch([]))
            return self._result("rules", await self.current_batch(user))
        labels = candidate_labels(set(selectable))
        cohort = (await self.cohorts.build(user.id)).get(found.monster.code)
        context: dict[str, Any] = {
            "answers": {key: value for key, value in answers.model_dump().items() if value != "unknown"},
            "cohort": self.cohorts.llm_context(cohort) if cohort else None,
            "candidates": [
                {"label": label, **candidate_context(selectable[code], found.goals.get(selectable[code].id))}
                for label, code in labels.items()
            ],
            "cards": [
                {"card_id": c.card_id, "challenge_code": c.challenge_code, "guidance": c.guidance} for c in cards
            ],
        }
        if activity is not None:
            context["activity_level"] = activity_level
            context["activity_answers"] = activity.model_dump()
        provider = self.provider if self.enabled else None
        record_id = await self.conversation._record_id(user.id)
        fingerprint = _fingerprint(
            context=context,
            cycle_id=found.cycle.id,
            record_id=record_id,
            model_version=found.model_version,
            provider=provider.model_version if provider else "fixed-questions",
            cards=[(card.card_id, card.version) for card in cards],
            goals={code: found.goals.get(challenge.id) for code, challenge in selectable.items()},
        )
        sources = [f"card:{card.card_id}" for card in cards]
        cached = await self._cached(user, found, fingerprint)
        if cached is not None:
            return replace(cached, sources=sources)
        served = {code: goal_numbers(display_goal(c, found.goals.get(c.id))) for code, c in selectable.items()}
        given = answers.model_dump()
        reasons = {
            code: self.index.question_page(ANSWER_FIELDS[code]).reason_for(given[ANSWER_FIELDS[code]])
            for code in selectable
        }
        try:
            # 후보가 하나면 고를 것이 없어 판단 모델을 부르지 않는다
            if provider is None:
                probabilities = {code: 1.0 / len(labels) for code in labels.values()}
            elif len(labels) == 1:
                probabilities = {code: 1.0 for code in labels.values()}
            else:
                probabilities = validate_judgment(await provider.judge(context, list(labels)), labels)
            decided = rank_selections(probabilities, selectable, cards, answers, reasons, served)
        except (ValueError, AppError, OSError, TimeoutError, httpx.HTTPError) as exc:
            # 모델 실패 내용·대화 원문·토큰을 로그에 남기지 않는다.
            # 키 오류(401)·모델 이름 오류(404)를 알 수 있게 예외 종류와 상태만 남긴다
            logger.warning("질의 챗봇 선택 호출·검증 실패, 규칙 추천으로 돌린다: %s", failure_label(exc))
            provider = None
            decided = (
                rank_selections(
                    {code: 1.0 / len(labels) for code in labels.values()}, selectable, cards, answers, reasons, served
                )
                if activity is not None
                else []
            )
        if not decided:
            if activity is not None:
                return self._result("hold", found.batch([]), sources=sources)
            return self._result("rules", await self.current_batch(user), sources=sources)
        return await self._commit(
            user,
            found,
            decided,
            now,
            record_id,
            fingerprint,
            answers,
            asked,
            sources,
            provider.model_version if provider else None,
            activity,
            activity_level,
        )

    async def current_batch(self, user: User) -> GeneratedRecommendations:
        """지금 주기에서 아직 응답하지 않은 마지막 추천 묶음. 없으면 규칙 추천을 새로 만든다 (CHLG-01)."""
        now = datetime.now(config.TIMEZONE)
        await self.rules.cycles.close_expired(user.id, today_kst(now), now)
        cycle = await self.rules.cycles.get_current(user.id)
        artifact = self.rules.artifact_source()
        if cycle is None or artifact is None:
            return await self.rules.generate(user, now)
        rows = await ChallengeRecommendation.filter(user_id=user.id, cycle_id=cycle.id, action__isnull=True).order_by(
            "-recommended_at", "rank", "id"
        )
        rows = [row for row in rows if row.recommended_at == rows[0].recommended_at] if rows else []
        blocked = await self.rules._blocked_challenge_ids(user.id, now)
        if not rows or any(row.challenge_id in blocked for row in rows):
            return await self.rules.generate(user, now)
        active = UserChallenge.filter(user_id=user.id, status=UserChallengeStatus.ACTIVE)
        challenges = {item.id: item for item in await Challenge.filter(id__in=[row.challenge_id for row in rows])}
        return GeneratedRecommendations(
            items=rows,
            challenges=challenges,
            cycle=cycle,
            monster=await self.rules.cycles.target_monster(cycle),
            model_version=artifact.model_version,
            model_experimental=artifact.experimental,
            remaining_slots=self.rules.cycles.remaining_slots(
                cycle, await active.filter(cycle_id=cycle.id).count(), await active.count(), today_kst(now)
            ),
        )

    def _feasible(self, found: EligibleChallenges) -> dict[str, Challenge]:
        """지금 고를 수 있는 코드. 1단계 21개 중 공략 대상·쿨다운·고정 계약을 통과한 후보만 남는다."""
        return {
            challenge.code: challenge
            for challenge, _ in found.scored
            if challenge.code in SUPPORTED_CODES and self.conversation._matches_fixed_contract(challenge)
        }

    async def _choose_question(
        self, fallback: QuestionPage, codes: set[str], answers: SituationAnswers, asked: list[str]
    ) -> QuestionPage:
        """열린 후보의 질문만 모델이 고르게 하고 잘못 고르면 고정 질문을 쓴다."""
        choose = getattr(self.provider, "choose_question", None) if self.enabled else None
        values = answers.model_dump()
        candidates = {
            ANSWER_FIELDS[code]: code
            for code in codes & SUPPORTED_CODES
            if values[ANSWER_FIELDS[code]] == "unknown" and ANSWER_FIELDS[code] not in asked
        }
        if choose is None or len(candidates) < 2:
            return fallback
        context = {
            "answers": {key: value for key, value in values.items() if value != "unknown"},
            "candidates": [
                {"answer_key": key, "challenge_code": code, "intent": self.index.question_page(key).text}
                for key, code in sorted(candidates.items())
            ],
        }
        try:
            result = await choose(context)
            key = result.get("answer_key") if isinstance(result, dict) else None
            if not isinstance(key, str) or key not in candidates:
                raise ValueError("질문 키가 현재 후보에 없습니다.")
            return self.index.question_page(key)
        except (ValueError, TypeError, KeyError, AppError, OSError, TimeoutError, httpx.HTTPError) as exc:
            logger.warning("질문 순서 판단 실패, 고정 질문으로 돌린다: %s", failure_label(exc))
            return fallback

    async def _question(self, question: QuestionPage, answers: SituationAnswers) -> dict[str, Any]:
        """생성 결과를 검사하고 실패하면 승인된 질문 페이지를 사용한다."""
        fallback = question_body(question)
        generate = getattr(self.provider, "generate_question", None)
        if generate is None:
            return fallback

        code = CODE_BY_ANSWER_KEY[question.answer_key]
        intents = [
            page.question.text
            for page in self.index.pages
            if page.question is not None and page.question.answer_key == question.answer_key
        ]
        allowed_labels = {
            option["value"]: sorted({option["label"]} | ANSWER_LABEL_VARIANTS.get(option["value"], set()))
            for option in fallback["options"]
        }
        context = {
            "answer_key": question.answer_key,
            "challenge_code": code,
            "intent": question.text,
            "intents": intents,
            "options": fallback["options"],
            "allowed_labels": allowed_labels,
            "answers": {key: value for key, value in answers.model_dump().items() if value != "unknown"},
        }
        try:
            result = await generate(context)
            if not isinstance(result, dict) or set(result) != {"text", "options"}:
                raise ValueError("질문 형식이 올바르지 않습니다.")
            text = result["text"]
            options = result["options"]
            if (
                code not in SUPPORTED_CODES
                or not isinstance(text, str)
                or not text.strip()
                or len(text) > 200
                or any(word in text and word not in question.text for word in PERIOD_WORDS)
                or set(re.findall(r"\d+", text)) != set(re.findall(r"\d+", question.text))
                or text.count("?") > 1
                or CLAIM_PATTERN.search(text)
                or not isinstance(options, list)
                or any(not isinstance(option, dict) or set(option) != {"value", "label"} for option in options)
                or len(options) != len(fallback["options"])
                or {option["value"] for option in options} != set(allowed_labels)
                or any(
                    not isinstance(option["label"], str)
                    or not option["label"].strip()
                    or len(option["label"]) > 80
                    or CLAIM_PATTERN.search(option["label"])
                    for option in options
                )
                or len({option["label"] for option in options}) != len(options)
            ):
                raise ValueError("질문이 승인된 값과 일치하지 않습니다.")
            approved = text in {prefix + intent for prefix in QUESTION_PREFIXES for intent in intents} and all(
                option["label"] in allowed_labels[option["value"]] for option in options
            )
            if not approved:
                verify = getattr(self.provider, "verify_question", None)
                if verify is None:
                    raise ValueError("새 질문을 검토할 수 없습니다.")
                review = await verify({"intent": question.text, "options": fallback["options"], "generated": result})
                if (
                    not isinstance(review, dict)
                    or set(review) != {"safe_and_equivalent"}
                    or review["safe_and_equivalent"] is not True
                ):
                    raise ValueError("생성 질문의 의미를 확인하지 못했습니다.")
            rendered = next(
                (
                    page.question
                    for page in self.index.pages
                    if page.question is not None
                    and page.question.answer_key == question.answer_key
                    and text in {prefix + page.question.text for prefix in QUESTION_PREFIXES}
                ),
                question,
            )
            return {**fallback, "question_id": rendered.question_id, "text": text, "options": options}
        except (ValueError, TypeError, KeyError, AppError, OSError, TimeoutError, httpx.HTTPError) as exc:
            logger.warning("질의 생성 호출·검증 실패, 고정 질문으로 돌린다: %s", failure_label(exc))
            return fallback

    def _context_cards(self, selectable: dict[str, Challenge]) -> list[EvidenceCard]:
        """후보마다 승인 카드 한 장을 먼저 넣고, 나머지 승인 카드로 채운다."""
        approved = [
            page.card
            for page in self.index.pages_for(set(selectable), {"card"})
            if page.card is not None and page.card.status == "approved"
        ]
        first_per_code: dict[str, EvidenceCard] = {}
        for card in approved:
            first_per_code.setdefault(card.challenge_code, card)
        ordered: dict[str, EvidenceCard] = {}
        for card in [*first_per_code.values(), *approved]:
            ordered.setdefault(card.card_id, card)
        return list(ordered.values())[: max(MAX_CONTEXT_CARDS, len(first_per_code))]

    async def _cached(self, user: User, found: EligibleChallenges, fingerprint: str) -> ChatResult | None:
        """같은 입력으로 이미 저장한 선택. 디시전 모델을 다시 부르지 않는다."""
        rows = await ChallengeRecommendation.filter(
            user_id=user.id, cycle_id=found.cycle.id, action__isnull=True, llm_model_version__isnull=False
        ).order_by("-recommended_at", "rank")
        stored = [
            row
            for row in rows
            if (row.conversation_snapshot or {}).get("fingerprint") == fingerprint
            and (row.conversation_snapshot or {}).get("policy_version") == CHAT_POLICY_VERSION
        ]
        if not stored:
            return None
        stored = [row for row in stored if row.recommended_at == stored[0].recommended_at]
        challenges = {item.id: item for item in await Challenge.filter(id__in=[row.challenge_id for row in stored])}
        return ChatResult(
            "conversation",
            FALLBACK_ANSWERS["conversation"],
            replace(found.batch(stored), challenges=challenges),
            [],
            {row.id: str((row.conversation_snapshot or {}).get("reason", "")) for row in stored},
            [],
        )

    async def _commit(
        self,
        user: User,
        found: EligibleChallenges,
        decided: list[ValidatedSelection],
        now: datetime,
        record_id: int | None,
        fingerprint: str,
        answers: SituationAnswers,
        asked: list[str],
        sources: list[str],
        llm_model_version: str | None,
        activity: ActivityAnswers | None,
        activity_level: int | None,
    ) -> ChatResult:
        """모델 호출 사이에 주기·건강기록·후보가 바뀌지 않았는지 잠금 안에서 다시 보고 추천 행을 만든다."""
        async with in_transaction():
            await lock_user(user.id)
            try:
                fresh = await self.rules.eligible(user, now)
            except AppError:
                return self._result("hold", found.batch([]), sources=sources)
            scores = {challenge.id: factor for challenge, factor in fresh.scored}
            if (
                fresh.cycle.id != found.cycle.id
                or fresh.model_version != found.model_version
                or await self.conversation._record_id(user.id) != record_id
                or any(selection.challenge.id not in scores for selection in decided)
                or any(fresh.goals.get(s.challenge.id) != found.goals.get(s.challenge.id) for s in decided)
            ):
                return self._result("hold", fresh.batch([]), sources=sources)
            rows, reasons = [], {}
            for rank, selection in enumerate(decided, 1):
                challenge, factor = selection.challenge, scores[selection.challenge.id]
                row = await ChallengeRecommendation.create(
                    user_id=user.id,
                    challenge_id=challenge.id,
                    cycle_id=fresh.cycle.id,
                    source_type=factor.source_type,
                    factor_key=challenge.factor_key,
                    factor_score=Decimal(str(round(factor.score, 5))),
                    rank=rank,
                    recommended_at=now,
                    # 목표 값은 AI 가 아니라 규칙이 정한 단계(없으면 마스터)다
                    proposed_goal=fresh.goals.get(challenge.id),
                    evidence_card_ids=[card.card_id for card in selection.cards],
                    llm_model_version=llm_model_version,
                    conversation_snapshot={
                        "policy_version": CHAT_POLICY_VERSION,
                        "fingerprint": fingerprint,
                        "answers": answers.model_dump(),
                        "asked": asked,
                        "card_versions": {card.card_id: card.version for card in selection.cards},
                        "model_version": fresh.model_version,
                        "health_record_id": record_id,
                        "reason": selection.reason,
                        "reason_replaced": selection.reason_replaced,
                        "probability": round(selection.probability, 4) if llm_model_version else None,
                        "activity_answers": activity.model_dump() if activity else None,
                        "activity_level": activity_level,
                    },
                )
                rows.append(row)
                reasons[row.id] = selection.reason
            return ChatResult("conversation", FALLBACK_ANSWERS["conversation"], fresh.batch(rows), [], reasons, sources)

    @staticmethod
    def _result(
        mode: ChatMode,
        generated: GeneratedRecommendations,
        *,
        questions: list[dict[str, Any]] | None = None,
        sources: list[str] | None = None,
    ) -> ChatResult:
        return ChatResult(mode, FALLBACK_ANSWERS[mode], generated, questions or [], {}, sources or [])


def question_body(question: QuestionPage) -> dict[str, Any]:
    """화면에 그릴 질문 한 장. 선택지 문구도 질문 페이지에서 온다. 이유 문장은 보내지 않는다."""
    return {
        "key": question.answer_key,
        "question_id": question.question_id,
        "text": question.text,
        "options": [{"value": option.value, "label": option.label} for option in question.options],
    }


def candidate_context(challenge: Challenge, proposed_goal: dict[str, Any] | None) -> dict[str, Any]:
    """선택 단계에 보여 줄 후보. 목표는 규칙이 정한 값을 읽기 전용으로만 넘긴다(출력 스키마에는 값 필드가 없다).

    이유 문장에 숫자를 쓰려면 이 값과 같아야 한다.
    """
    goal = display_goal(challenge, proposed_goal)
    return {
        "challenge_code": challenge.code,
        "title": goal.title or challenge.title,
        "context_label": challenge.context_label,
        "difficulty": goal.difficulty,
        "served_goal": {
            "target_value": float(goal.target_value) if goal.target_value is not None else None,
            "unit": challenge.unit,
            "daily_target_count": goal.daily_target_count,
        },
    }


def _fingerprint(**parts: Any) -> str:
    raw = json.dumps({**parts, "policy": CHAT_POLICY_VERSION}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def activity_assessment_question(activity: ActivityAnswers) -> dict[str, Any] | None:
    """답하지 않은 운동 범위 질문 한 개를 반환한다."""
    if activity.light in {"unknown", "unsure"}:
        key, text = "light", "작은 공간에서 가볍게 몸을 움직일 수 있나요?"
    elif activity.light == "yes" and activity.walk in {"unknown", "unsure"}:
        key, text = "walk", "밖에 나가 산책할 수 있나요?"
    elif activity.light == "yes" and activity.walk == "yes" and activity.vigorous in {"unknown", "unsure"}:
        key, text = "vigorous", "조깅이나 팔굽혀펴기를 할 공간과 여유가 있나요?"
    else:
        return None
    return {
        "key": f"activity_{key}",
        "question_id": f"activity-{key}",
        "text": f"다시 확인할게요. {text}" if getattr(activity, key) == "unsure" else text,
        "options": [
            {"value": "yes", "label": "할 수 있어요"},
            {"value": "no", "label": "어려워요"},
            {"value": "unsure", "label": "잘 모르겠어요"},
            {"value": "limited", "label": "몸 상태 때문에 어려워요"},
        ],
    }
