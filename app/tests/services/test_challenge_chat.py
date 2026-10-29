"""질의 챗봇: 1단계 대화 · 2단계 선택(디시전 모델) · 저장 · 서빙 값. 실제 LLM 은 부르지 않는다."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from tortoise.contrib.test import TestCase

from app.apis.v1.challenge_chat_routers import chat_setup_issue, get_challenge_chat_service
from app.core import config
from app.dependencies.security import get_request_user
from app.main import app
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeRecommendation,
    UserAttackCycle,
    UserChallenge,
    UserChallengeStatus,
    UserMonster,
)
from app.models.health_records import HealthRecord
from app.models.predictions import Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.services.attack_cycles import CYCLE_POLICY_VERSION
from app.services.challenge_chat import (
    CHAT_POLICY_VERSION,
    FALLBACK_REPLIES,
    ChallengeChatService,
    redact,
)
from app.services.challenge_goals import goal_policy
from app.services.challenge_selections import FALLBACK_REASON, decision_schema, has_unsafe_claim, reason_is_safe
from app.services.monster_cohorts import MonsterCohortService, completion_band
from app.services.page_index import PageIndex
from app.services.rag_cards import SituationAnswers
from app.services.recommendations import RecommendationService, challenge_goal_body
from app.tests.d_fixtures import TEST_MODEL_VERSION, fake_artifact, make_target
from app.tests.prediction_apis.helpers import login
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

DELAY = "CH_DELAY_FIRST_CIG"
NO_SMOKE = "CH_NO_SMOKE_TODAY"
YES = SituationAnswers(first_cig="yes", no_smoke="yes")
ARTIFACT = fake_artifact({"hypertension": {"smoking_current": 70.0}}, p95={"diabetes": {"smoking_current": 0.0128}})
CONVERSATION = [
    {"role": "user", "content": "아침에 일어나자마자 담배를 피워요. 메일 a@b.com"},
    {"role": "assistant", "content": "아침 첫 담배를 조금 미뤄 보는 건 어떨까요?"},
    {"role": "user", "content": "아침 담배 미루기 해 볼게요"},
]


def delay_pick(**overrides: Any) -> dict[str, Any]:
    item = {
        "challenge_code": DELAY,
        "evidence_card_ids": ["C43"],
        "reason": "아침에 일어난 뒤 첫 담배를 조금 늦추는 것부터 해 볼 수 있어요.",
    }
    return {"selections": [{**item, **overrides}]}


class FixtureProvider:
    model_version = "fixture-chat"

    def __init__(self, decision: Any = None, reply: str = "", error: Exception | None = None) -> None:
        self.decision, self.reply, self.error = decision, reply, error
        self.decide_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.chat_calls: list[tuple[dict[str, Any], list[dict[str, str]]]] = []

    async def chat(self, context: dict[str, Any], messages: list[dict[str, str]]) -> str:
        self.chat_calls.append((context, messages))
        if self.error:
            raise self.error
        return self.reply

    async def decide(self, context: dict[str, Any], schema: dict[str, Any]) -> Any:
        self.decide_calls.append((context, schema))
        if self.error:
            raise self.error
        return self.decision


# ---------------------------------------------------------------- 순수 함수


def test_redact_hides_contacts_and_long_numbers() -> None:
    text = redact("제 메일은 a.b@example.com 이고 010-1234-5678, 주민 9001011234567 입니다")
    assert "example" not in text and "1234" not in text and "9001011234567" not in text


@pytest.mark.parametrize(
    ("text", "allow_numbers", "unsafe"),
    [
        ("첫 담배를 늦추는 것부터 해 봐요.", False, False),
        ("혈압을 낮춰 줍니다.", False, True),
        ("당뇨를 예방할 수 있어요.", True, True),
        ("30분 미루기부터 해 봐요.", False, True),
        ("30분 미루기부터 해 봐요.", True, False),
        ("성공률 80% 입니다.", True, True),
    ],
)
def test_unsafe_claims(text: str, allow_numbers: bool, unsafe: bool) -> None:
    assert has_unsafe_claim(text, allow_numbers=allow_numbers) is unsafe


@pytest.mark.parametrize(
    ("reason", "safe"),
    [
        ("저녁에 20분 걸어 보는 건 어떨까요?", True),  # 서빙 목표 20분과 같은 숫자
        ("하루 1번 해 볼 수 있어요.", True),  # 하루 횟수
        ("저녁에 30분 걸어 보세요.", False),  # 서빙 값과 다른 숫자
        ("저녁에 20분 이어서 걸을 시간이 있다고 답한 경우에만 저녁 20분 걷기를 제안한다.", False),  # 운영자 말투
        ("혈당을 확실히 낮춰 줘요.", False),
        ("", False),
    ],
)
def test_reason_allows_only_served_numbers_in_user_tone(reason: str, safe: bool) -> None:
    assert reason_is_safe(reason, {Decimal("20"), Decimal("1")}) is safe


def test_completion_band_follows_the_cycle_rule() -> None:
    assert [completion_band(v) for v in (None, Decimal("0.8"), Decimal("0.5"), Decimal("0.4999"))] == [
        "none",
        "high",
        "middle",
        "low",
    ]


def _objects(schema: Any) -> list[dict[str, Any]]:
    if isinstance(schema, dict):
        found = [schema] if schema.get("type") == "object" else []
        return found + [o for value in schema.values() for o in _objects(value)]
    if isinstance(schema, list):
        return [o for item in schema for o in _objects(item)]
    return []


def test_decision_schema_ties_each_code_to_its_own_cards() -> None:
    schema = decision_schema({NO_SMOKE: ["C20", "C19"], DELAY: ["C43"], "CH_STAIRS": []})
    # Structured Outputs(strict) 규칙: 모든 객체가 추가 키를 막고 모든 속성을 required 로 둔다
    for obj in _objects(schema):
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])
    branches = schema["properties"]["selections"]["items"]["anyOf"]
    allowed = {b["properties"]["challenge_code"]["enum"][0]: b["properties"]["evidence_card_ids"] for b in branches}
    # 카드가 없는 코드는 고를 수 없고, 코드마다 자기 카드만 붙일 수 있다
    assert {code: cards["items"]["enum"] for code, cards in allowed.items()} == {
        DELAY: ["C43"],
        NO_SMOKE: ["C19", "C20"],
    }
    # 목표 값 필드는 스키마에 없다. AI 는 값을 낼 수 없다
    assert all(set(b["properties"]) == {"challenge_code", "evidence_card_ids", "reason"} for b in branches)
    with pytest.raises(ValueError):
        decision_schema({DELAY: []})


# ---------------------------------------------------------------- DB


class TestChallengeChat(TestCase):
    async def _ready(self, email: str) -> tuple[User, UserMonster]:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        await (
            Challenge.filter(factor_key="smoking_current").exclude(code__in=[DELAY, NO_SMOKE]).update(is_enabled=False)
        )
        user = await User.create(email=email, password_hash="x", nickname="t", htn_diagnosed=True)
        target = await make_target(user.id, ["smoking_current"])
        now = datetime.now(config.TIMEZONE)
        record = await HealthRecord.create(user_id=user.id, recorded_at=now, smoking_current=True, sbp=150)
        prediction = await Prediction.create(
            user_id=user.id,
            health_record_id=record.id,
            job_id=f"chat-{user.id}",
            model_version=TEST_MODEL_VERSION,
            status=PredictionStatus.DONE,
            dm_probability=Decimal("0.3"),
            predicted_at=now,
        )
        await PredictionContribution.create(
            prediction_id=prediction.id,
            disease="diabetes",
            factor_key="smoking_current",
            contribution=Decimal("0.0064"),
            direction="increase",
            rank=1,
        )
        return user, target

    async def _finished(self, user: User, target: UserMonster, rate: str, level: int) -> UserChallenge:
        """지난 주기에 기간 종료로 끝난 미뤄 피우기 미션."""
        challenge = await Challenge.get(code=DELAY)
        policy = goal_policy(challenge)
        assert policy is not None
        start = datetime.now(config.TIMEZONE).date() - timedelta(days=30)
        cycle = await UserAttackCycle.create(
            user_id=user.id,
            target_user_monster_id=target.id,
            status=AttackCycleStatus.COMPLETED,
            policy_version=CYCLE_POLICY_VERSION,
            start_date=start,
            end_date=start + timedelta(days=27),
        )
        return await UserChallenge.create(
            user_id=user.id,
            challenge_id=challenge.id,
            cycle_id=cycle.id,
            status=UserChallengeStatus.GRADUATED,
            start_date=start,
            end_date=start + timedelta(days=27),
            daily_target_count_snapshot=1,
            duration_days_snapshot=28,
            completion_rate=Decimal(rate),
            goal_config_snapshot={"level": level, "policy_version": policy.version},
        )

    async def _service(self, provider: FixtureProvider | None, *, enabled: bool = True) -> ChallengeChatService:
        return ChallengeChatService(
            RecommendationService(lambda: ARTIFACT), await PageIndex.build(), provider, enabled=enabled
        )

    async def _chat_rows(self, user: User) -> list[ChallengeRecommendation]:
        return await ChallengeRecommendation.filter(user_id=user.id, llm_model_version__isnull=False).order_by("id")

    # -------------------------------------------------------- Page Index

    async def test_page_index_holds_cards_master_and_step_tables(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        index = await PageIndex.build()
        kinds = [page.kind for page in index.pages]
        assert kinds.count("card") == 48
        assert kinds.count("challenge") == await Challenge.all().count() == 33
        assert kinds.count("steps") == sum(1 for c in await Challenge.all() if goal_policy(c) is not None) == 9
        assert index.by_id["steps:CH_DELAY_FIRST_CIG"].body.startswith("1단계: 아침 첫 담배 15분 미루기")

    async def test_search_returns_only_approved_cards_the_user_can_do(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        index = await PageIndex.build()
        hits = index.search("아침 담배 미루기", {DELAY}, YES)
        assert hits and all(page.challenge_code == DELAY for page in hits)
        # 못 한다고 답한 챌린지의 카드는 나오지 않는다
        assert not [p for p in index.search("아침 담배", {DELAY}, SituationAnswers(first_cig="no")) if p.card]
        assert index.search("전혀 관계없는 질문", {DELAY}, YES) == []

    # -------------------------------------------------------- 코호트

    async def test_cohort_groups_missions_by_monster_without_raw_values(self) -> None:
        user, target = await self._ready("chat-cohort@example.com")
        await self._finished(user, target, "0.8500", level=2)
        await RecommendationService(lambda: ARTIFACT).generate(user)

        cohorts = await MonsterCohortService().build(user.id)
        [mine] = [cohort for cohort in cohorts.values() if cohort.is_target]
        assert [m.challenge_code for m in mine.finished] == [DELAY]
        assert mine.health_record_ids and mine.prediction_ids
        context = MonsterCohortService.llm_context(mine)
        assert context["history"] == [{"challenge_code": DELAY, "level": 2, "completion": "high"}]
        assert "150" not in str(context) and "0.85" not in str(context)

    # -------------------------------------------------------- 1단계 대화

    async def test_reply_talks_inside_the_candidates_without_saving(self) -> None:
        user, _ = await self._ready("chat-reply@example.com")
        provider = FixtureProvider(reply="아침 첫 담배를 조금 미뤄 보는 건 어떨까요? 보통 몇 시에 일어나세요?")
        result = await (await self._service(provider)).reply(user, CONVERSATION)

        assert result.mode == "chat" and result.reply.startswith("아침 첫 담배")
        [(context, messages)] = provider.chat_calls
        assert set(context) == {"candidates", "pages"}
        assert {c["challenge_code"] for c in context["candidates"]} == {DELAY, NO_SMOKE}
        # 대화에서도 목표 숫자는 서빙할 값만 쓰도록 읽기 전용으로 넘긴다
        assert all("served_goal" in c for c in context["candidates"])
        assert "a@b.com" not in str(messages) and "150" not in str(context)
        assert "challenge:CH_DELAY_FIRST_CIG" in result.sources
        assert not await self._chat_rows(user)

    async def test_reply_with_health_claims_or_errors_uses_a_fixed_sentence(self) -> None:
        user, _ = await self._ready("chat-reply-bad@example.com")
        unsafe = await (await self._service(FixtureProvider(reply="혈압을 확실히 낮춰 줘요."))).reply(
            user, CONVERSATION
        )
        failed = await (await self._service(FixtureProvider(error=TimeoutError()))).reply(user, CONVERSATION)
        off = await (await self._service(FixtureProvider(), enabled=False)).reply(user, CONVERSATION)
        assert unsafe.reply == FALLBACK_REPLIES["unsafe"]
        assert failed.reply == FALLBACK_REPLIES["error"]
        assert (off.mode, off.reply) == ("off", FALLBACK_REPLIES["off"])

    # -------------------------------------------------------- 2단계 선택

    async def test_disabled_selection_returns_the_rule_cards(self) -> None:
        user, _ = await self._ready("chat-off@example.com")
        provider = FixtureProvider()
        result = await (await self._service(provider, enabled=False)).select(user, CONVERSATION, YES, [])
        assert result.mode == "rules" and result.recommendations.items and provider.decide_calls == []

    async def test_unknown_answers_ask_first(self) -> None:
        user, _ = await self._ready("chat-ask@example.com")
        result = await (await self._service(FixtureProvider())).select(user, CONVERSATION, SituationAnswers(), [])
        assert result.mode == "ask"
        assert {q["key"] for q in result.questions} == {"first_cig", "no_smoke"}

    async def test_selection_is_saved_with_rule_values_and_served(self) -> None:
        # 지난 주기 2단계 85% → 규칙이 3단계로 올린다. AI 는 고르기만 하고 값은 규칙 그대로 서빙한다
        user, target = await self._ready("chat-save@example.com")
        await self._finished(user, target, "0.8500", level=2)
        provider = FixtureProvider(delay_pick())
        service = await self._service(provider)

        result = await service.select(user, CONVERSATION, YES, ["first_cig", "no_smoke"])

        assert result.mode == "conversation"
        [row] = result.recommendations.items
        challenge = await Challenge.get(code=DELAY)
        assert row.challenge_id == challenge.id and row.rank == 1
        assert row.proposed_goal is not None and row.proposed_goal["level"] == 3
        basis = row.proposed_goal["basis"]
        assert isinstance(basis, dict) and basis["direction"] == "up"
        assert row.evidence_card_ids == ["C43"] and row.llm_model_version == "fixture-chat"
        snapshot = row.conversation_snapshot or {}
        assert snapshot["policy_version"] == CHAT_POLICY_VERSION
        assert str(snapshot["reason"]).startswith("아침에 일어난 뒤")
        assert "a@b.com" not in str(snapshot)
        served = challenge_goal_body(challenge, row.proposed_goal)
        assert served["goal_level"] == 3 and served["safety_check_required"] is True

        # 보낸 입력: 가린 대화·범주 요약·후보·카드. 목표 값·건강 수치·이메일은 없다
        [(context, schema)] = provider.decide_calls
        assert set(context) == {"conversation", "answers", "cohort", "candidates", "cards"}
        assert "a@b.com" not in str(context) and "150" not in str(context)
        # 후보의 목표 값은 규칙이 정한 값을 읽기 전용으로만 넘긴다. 출력 스키마에는 값 필드가 없다
        [delay_context] = [c for c in context["candidates"] if c["challenge_code"] == DELAY]
        assert delay_context["served_goal"]["target_value"] == served["target_value"]
        branches = schema["properties"]["selections"]["items"]["anyOf"]
        allowed = {b["properties"]["challenge_code"]["enum"][0]: b for b in branches}
        assert set(allowed) == {DELAY, NO_SMOKE}
        assert "C43" in allowed[DELAY]["properties"]["evidence_card_ids"]["items"]["enum"]

        # 같은 입력은 저장한 결과를 돌려주고 디시전 모델을 다시 부르지 않는다
        again = await service.select(user, CONVERSATION, YES, ["first_cig", "no_smoke"])
        assert again.mode == "conversation" and [r.id for r in again.recommendations.items] == [row.id]
        assert len(provider.decide_calls) == 1
        # 시작은 클라이언트가 CHLG-05 로 한다
        assert not await UserChallenge.filter(user_id=user.id, cycle_id=row.cycle_id).exists()

    async def test_invalid_selections_fall_back_to_rules_without_saving(self) -> None:
        cases = [
            delay_pick(challenge_code="CH_STAIRS"),  # 고를 수 있는 코드 밖
            delay_pick(challenge_code="CH_CHECK_LABEL"),  # 21개 밖
            delay_pick(evidence_card_ids=["C01"]),  # 다른 챌린지 카드
            {"selections": [{**delay_pick()["selections"][0], "target_value": 30}]},  # AI 가 값을 낸 경우
            {"selections": [delay_pick()["selections"][0]] * 2},  # 같은 코드 두 번
        ]
        for number, output in enumerate(cases):
            user, _ = await self._ready(f"chat-bad{number}@example.com")
            result = await (await self._service(FixtureProvider(output))).select(user, CONVERSATION, YES, [])
            assert result.mode == "rules", output
            assert not await self._chat_rows(user)

    async def test_empty_selection_falls_back_to_rules(self) -> None:
        user, _ = await self._ready("chat-empty@example.com")
        result = await (await self._service(FixtureProvider({"selections": []}))).select(user, CONVERSATION, YES, [])
        assert result.mode == "rules" and result.recommendations.items

    async def test_wrong_key_falls_back_and_logs_only_the_status(self) -> None:
        user, _ = await self._ready("chat-401@example.com")
        request = httpx.Request("POST", "https://api.openai.com/v1/responses", headers={"Authorization": "Bearer sk-x"})
        error = httpx.HTTPStatusError("401", request=request, response=httpx.Response(401, request=request))
        with self.assertLogs("app.services.challenge_chat", "WARNING") as logs:
            result = await (await self._service(FixtureProvider(error=error))).select(user, CONVERSATION, YES, [])
        assert result.mode == "rules"
        assert logs.output == [
            "WARNING:app.services.challenge_chat:질의 챗봇 선택 호출·검증 실패, 규칙 추천으로 돌린다: HTTPStatusError 401"
        ]

    async def test_unsafe_reason_is_replaced_by_the_card(self) -> None:
        user, _ = await self._ready("chat-claim@example.com")
        output = delay_pick(reason="혈압을 확실히 낮춰요.")
        result = await (await self._service(FixtureProvider(output))).select(user, CONVERSATION, YES, [])
        [row] = result.recommendations.items
        assert result.reasons[row.id] == FALLBACK_REASON
        assert (row.conversation_snapshot or {})["reason_replaced"] is True

    async def test_selected_challenge_shows_up_as_a_normal_recommendation_card(self) -> None:
        """대화로 고른 추천은 CHLG-02 목록(전투 화면 카드)에 같은 값으로 나타나고 CHLG-05 로 시작할 수 있다."""
        user, _ = await self._ready("chat-card@example.com")
        service = await self._service(FixtureProvider(delay_pick()))
        app.dependency_overrides[get_challenge_chat_service] = lambda: service
        app.dependency_overrides[get_request_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                body = {"messages": CONVERSATION, "answers": YES.model_dump(), "asked": ["first_cig", "no_smoke"]}
                selected = (await client.post("/api/v1/challenge-chat/select", json=body)).json()["data"]
                listed = (await client.get("/api/v1/challenge-recommendations")).json()["data"]["items"]
                started = await client.post(
                    "/api/v1/user-challenges",
                    json={"recommendation_ids": [selected["items"][0]["recommendation_id"]], "safety_confirmed": True},
                )
        finally:
            app.dependency_overrides.clear()

        assert selected["mode"] == "conversation"
        [item] = selected["items"]
        card = next(row for row in listed if row["recommendation_id"] == item["recommendation_id"])
        # 전투 화면이 카드를 그릴 때 읽는 값은 대화 결과에도 모두 같은 값으로 있다
        shared = set(card) - {"proposed_goal", "action", "cooldown_choice", "exclude_until", "suppressed_until_manual"}
        assert {key: item[key] for key in shared} == {key: card[key] for key in shared}
        assert item["reason"] and item["evidence_card_ids"] == ["C43"]
        assert started.status_code == 201


class TestChallengeChatApi(TestCase):
    async def test_chat_endpoints_require_login_and_follow_the_rule_path(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            anonymous = await client.post(
                "/api/v1/challenge-chat", json={"messages": [{"role": "user", "content": "a"}]}
            )
            _, headers = await login(client, "chat-api@example.com")
            empty = await client.post("/api/v1/challenge-chat", json={"messages": []}, headers=headers)
            last_assistant = await client.post(
                "/api/v1/challenge-chat", json={"messages": [{"role": "assistant", "content": "a"}]}, headers=headers
            )
            off = await client.post(
                "/api/v1/challenge-chat", json={"messages": [{"role": "user", "content": "a"}]}, headers=headers
            )
            # 예측 전이라 규칙 추천(CHLG-01)과 같은 이유로 막힌다
            blocked = await client.post("/api/v1/challenge-chat/select", json={}, headers=headers)
        assert anonymous.status_code == 401
        assert empty.json()["error"]["code"] == last_assistant.json()["error"]["code"] == "VALIDATION_ERROR"
        assert off.json()["data"]["mode"] == "off"
        assert blocked.json()["error"]["code"] == "CHLG_RECOMMENDATION_UNAVAILABLE"

    async def test_chat_runs_on_rules_without_a_key(self) -> None:
        with (
            patch.object(config, "CHALLENGE_CHAT_ENABLED", True),
            patch.object(config, "OPENAI_API_KEY", SecretStr("  ")),
        ):
            service = await get_challenge_chat_service()
            issue = chat_setup_issue()
        assert service.provider is None and not service.enabled
        assert issue is not None and ".env" in issue and "OPENAI_API_KEY" in issue

    async def test_chat_uses_the_configured_model_when_a_key_is_set(self) -> None:
        with (
            patch.object(config, "CHALLENGE_CHAT_ENABLED", True),
            patch.object(config, "OPENAI_API_KEY", SecretStr("sk-test-secret")),
            patch.object(config, "OPENAI_MODEL", "gpt-4o"),
        ):
            service = await get_challenge_chat_service()
            issue = chat_setup_issue()
        assert service.enabled and service.provider is not None
        assert service.provider.model_version == "gpt-4o"
        assert issue is None and "sk-test-secret" not in repr(service.provider)


def test_setup_issue_names_the_switch_when_only_the_key_is_set() -> None:
    with (
        patch.object(config, "CHALLENGE_CHAT_ENABLED", False),
        patch.object(config, "OPENAI_API_KEY", SecretStr("sk-test-secret")),
    ):
        issue = chat_setup_issue()
    assert issue is not None and "CHALLENGE_CHAT_ENABLED=true" in issue and "sk-test-secret" not in issue
