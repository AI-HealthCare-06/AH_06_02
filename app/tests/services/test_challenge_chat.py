"""질의 챗봇: 선택형 질문(누른 답만) · 판단 모델(확률) 선택 · 저장 · 서빙 값. 실제 LLM 은 부르지 않는다."""

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
    ChallengeChatService,
)
from app.services.challenge_goals import goal_policy
from app.services.challenge_selections import (
    FALLBACK_REASON,
    candidate_labels,
    reason_is_safe,
    validate_judgment,
)
from app.services.monster_cohorts import MonsterCohortService, completion_band
from app.services.page_index import PageIndex
from app.services.rag_cards import SituationAnswers, question_bank
from app.services.recommendations import RecommendationService, challenge_goal_body
from app.tests.d_fixtures import TEST_MODEL_VERSION, fake_artifact, make_target
from app.tests.prediction_apis.helpers import login
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

DELAY = "CH_DELAY_FIRST_CIG"
NO_SMOKE = "CH_NO_SMOKE_TODAY"
YES = SituationAnswers(first_cig="yes", no_smoke="yes")
ARTIFACT = fake_artifact({"hypertension": {"smoking_current": 70.0}}, p95={"diabetes": {"smoking_current": 0.0128}})


#: 후보 라벨은 코드 순이다: A = 미뤄 피우기, B = 오늘 안 피우기
PREFER_DELAY = {"A": 0.8, "B": 0.2}


class FixtureProvider:
    model_version = "fixture-chat"

    def __init__(self, judgment: Any = None, error: Exception | None = None) -> None:
        self.judgment, self.error = judgment, error
        self.judge_calls: list[tuple[dict[str, Any], list[str]]] = []

    async def judge(self, context: dict[str, Any], labels: list[str]) -> Any:
        self.judge_calls.append((context, labels))
        if self.error:
            raise self.error
        return self.judgment


def reason_for(key: str, value: str) -> str | None:
    return next(page.reason_for(value) for page in question_bank() if page.answer_key == key)


# ---------------------------------------------------------------- 순수 함수


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


def test_labels_and_judgment_keep_only_candidate_probabilities() -> None:
    labels = candidate_labels({NO_SMOKE, DELAY})
    assert labels == {"A": DELAY, "B": NO_SMOKE}
    # 후보 라벨끼리 합이 1이 되게 다시 나눈다. 후보 밖 라벨은 버린다
    assert validate_judgment({"A": 0.6, "B": 0.2, "Z": 0.2}, labels) == pytest.approx({DELAY: 0.75, NO_SMOKE: 0.25})
    for bad in ({"Z": 0.9}, {"A": 0.3}, {"A": 2.0}, ["A"]):
        with pytest.raises(ValueError):
            validate_judgment(bad, labels)


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
        assert kinds.count("question") == len(question_bank()) == 42
        assert index.by_id["steps:CH_DELAY_FIRST_CIG"].body.startswith("1단계: 아침 첫 담배 15분 미루기")

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

    # -------------------------------------------------------- 질문·선택

    async def test_disabled_selection_returns_the_rule_cards(self) -> None:
        user, _ = await self._ready("chat-off@example.com")
        provider = FixtureProvider()
        result = await (await self._service(provider, enabled=False)).select(user, YES, [])
        assert result.mode == "rules" and result.recommendations.items and provider.judge_calls == []

    async def test_questions_come_one_by_one_from_pages_with_a_fixed_seed(self) -> None:
        user, _ = await self._ready("chat-ask@example.com")
        service = await self._service(FixtureProvider())
        first = await service.select(user, SituationAnswers(), [])
        assert first.mode == "ask" and len(first.questions) == 1
        [question] = first.questions
        assert question["key"] in {"first_cig", "no_smoke"}
        page = next(p for p in question_bank() if p.question_id == question["question_id"])
        assert question["text"] == page.text and page.answer_key == question["key"]
        # 선택지 문구도 질문 페이지에서 온다. 이유 문장은 화면에 보내지 않는다
        assert question["options"] == [{"value": o.value, "label": o.label} for o in page.options]
        # 같은 사람·같은 주기·같은 답이면 같은 질문
        assert (await service.select(user, SituationAnswers(), [])).questions == first.questions
        # 답하면 남은 답 키를 묻고, 더 물을 게 없으면 질문을 멈춘다
        answered = SituationAnswers.model_validate({question["key"]: "yes"})
        second = await service.select(user, answered, [question["key"]])
        assert (
            second.mode == "ask" and second.questions[0]["key"] == ({"first_cig", "no_smoke"} - {question["key"]}).pop()
        )
        # 활동 제한·알 수 없는 질문 기록
        assert (await service.select(user, SituationAnswers(first_cig="no"), ["first_cig", "no_smoke"])).mode != "ask"
        with pytest.raises(ValueError):
            await service.select(user, SituationAnswers(), ["unknown_key"])

    async def test_random_questions_spread_over_branches_and_stop_at_three(self) -> None:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        index = await PageIndex.build()
        codes = {"CH_WALK_AFTER_MEAL", "CH_STAIRS", "CH_STAND_HOURLY", "CH_SCREEN_BREAK", "CH_SQUAT_15"}
        picks = [index.next_question(codes, SituationAnswers(), [], f"user-{n}:1") for n in range(30)]
        drawn = {pick.answer_key for pick in picks if pick is not None}
        # 시드가 다르면 다른 질문이 나온다(코드 순서로 고정돼 있지 않다)
        assert len(drawn) >= 3
        asked: list[str] = []
        for _ in range(3):
            question = index.next_question(codes, SituationAnswers(), asked, "user-1:1")
            assert question is not None and question.answer_key not in asked
            asked.append(question.answer_key)
        assert index.next_question(codes, SituationAnswers(), asked, "user-1:1") is None
        assert index.next_question(codes, SituationAnswers(stairs="limited"), [], "user-1:1") is None

    async def test_selection_ranks_by_probability_and_fills_reason_from_the_page(self) -> None:
        # 지난 주기 2단계 85% → 규칙이 3단계로 올린다. AI 는 확률만 내고 값·문장은 서버가 채운다
        user, target = await self._ready("chat-save@example.com")
        await self._finished(user, target, "0.8500", level=2)
        provider = FixtureProvider(PREFER_DELAY)
        service = await self._service(provider)

        result = await service.select(user, YES, ["first_cig", "no_smoke"])

        assert result.mode == "conversation"
        first, second = result.recommendations.items
        challenge = await Challenge.get(code=DELAY)
        assert first.challenge_id == challenge.id and first.rank == 1 and second.rank == 2
        assert first.proposed_goal is not None and first.proposed_goal["level"] == 3
        basis = first.proposed_goal["basis"]
        assert isinstance(basis, dict) and basis["direction"] == "up"
        [card_id] = first.evidence_card_ids or []
        assert card_id.startswith("C") and first.llm_model_version == "fixture-chat"
        snapshot = first.conversation_snapshot or {}
        assert snapshot["policy_version"] == CHAT_POLICY_VERSION
        assert snapshot["probability"] == 0.8 and (second.conversation_snapshot or {})["probability"] == 0.2
        # 이유 문장은 답한 질문 페이지의 문장이다(모델이 만들지 않는다)
        assert result.reasons[first.id] == snapshot["reason"] == reason_for("first_cig", "yes")
        assert result.reasons[second.id] == reason_for("no_smoke", "yes")
        served = challenge_goal_body(challenge, first.proposed_goal)
        assert served["goal_level"] == 3 and served["safety_check_required"] is True

        # 보낸 입력: 누른 답·범주 요약·라벨 붙은 후보·카드. 자유 입력·건강 수치·이메일은 없다
        [(context, labels)] = provider.judge_calls
        assert set(context) == {"answers", "cohort", "candidates", "cards"}
        assert labels == ["A", "B"] and [c["label"] for c in context["candidates"]] == labels
        assert "150" not in str(context)
        [delay_context] = [c for c in context["candidates"] if c["challenge_code"] == DELAY]
        assert delay_context["served_goal"]["target_value"] == served["target_value"]

        # 같은 입력은 저장한 결과를 돌려주고 판단 모델을 다시 부르지 않는다
        again = await service.select(user, YES, ["first_cig", "no_smoke"])
        assert again.mode == "conversation" and [r.id for r in again.recommendations.items] == [first.id, second.id]
        assert len(provider.judge_calls) == 1
        # 시작은 클라이언트가 CHLG-05 로 한다
        assert not await UserChallenge.filter(user_id=user.id, cycle_id=first.cycle_id).exists()

    async def test_one_candidate_needs_no_model_call(self) -> None:
        user, _ = await self._ready("chat-single@example.com")
        provider = FixtureProvider(error=TimeoutError())
        answers = SituationAnswers(first_cig="yes", no_smoke="no")
        result = await (await self._service(provider)).select(user, answers, ["first_cig", "no_smoke"])
        [row] = result.recommendations.items
        assert result.mode == "conversation" and provider.judge_calls == []
        assert (row.conversation_snapshot or {})["probability"] == 1.0
        assert result.reasons[row.id] == reason_for("first_cig", "yes")

    async def test_unusable_judgments_fall_back_to_rules_without_saving(self) -> None:
        for number, judgment in enumerate([{"Z": 0.9}, {"A": 0.3}, ["A"], None]):
            user, _ = await self._ready(f"chat-bad{number}@example.com")
            result = await (await self._service(FixtureProvider(judgment))).select(user, YES, [])
            assert result.mode == "rules" and result.recommendations.items, judgment
            assert not await self._chat_rows(user)

    async def test_all_no_answers_fall_back_to_rules(self) -> None:
        user, _ = await self._ready("chat-none@example.com")
        answers = SituationAnswers(first_cig="no", no_smoke="no")
        provider = FixtureProvider(PREFER_DELAY)
        result = await (await self._service(provider)).select(user, answers, ["first_cig", "no_smoke"])
        assert result.mode == "rules" and result.recommendations.items and provider.judge_calls == []

    async def test_wrong_key_falls_back_and_logs_only_the_status(self) -> None:
        user, _ = await self._ready("chat-401@example.com")
        request = httpx.Request("POST", "https://api.openai.com/v1/responses", headers={"Authorization": "Bearer sk-x"})
        error = httpx.HTTPStatusError("401", request=request, response=httpx.Response(401, request=request))
        with self.assertLogs("app.services.challenge_chat", "WARNING") as logs:
            result = await (await self._service(FixtureProvider(error=error))).select(user, YES, [])
        assert result.mode == "rules"
        assert logs.output == [
            "WARNING:app.services.challenge_chat:질의 챗봇 선택 호출·검증 실패, 규칙 추천으로 돌린다: HTTPStatusError 401"
        ]

    async def test_reason_with_numbers_not_served_is_replaced(self) -> None:
        user, _ = await self._ready("chat-claim@example.com")
        service = await self._service(FixtureProvider(PREFER_DELAY))
        page = service.index.question_page("first_cig")
        unsafe = page.model_copy(
            update={
                "options": [
                    o.model_copy(update={"reason": "혈압을 확실히 낮춰요."}) if o.reason else o for o in page.options
                ]
            }
        )
        with patch.object(service.index, "question_page", lambda key: unsafe if key == "first_cig" else page):
            result = await service.select(user, YES, [])
        first = result.recommendations.items[0]
        assert result.reasons[first.id] == FALLBACK_REASON
        assert (first.conversation_snapshot or {})["reason_replaced"] is True

    async def test_selected_challenge_shows_up_as_a_normal_recommendation_card(self) -> None:
        """대화로 고른 추천은 CHLG-02 목록(전투 화면 카드)에 같은 값으로 나타나고 CHLG-05 로 시작할 수 있다."""
        user, _ = await self._ready("chat-card@example.com")
        service = await self._service(FixtureProvider(PREFER_DELAY))
        app.dependency_overrides[get_challenge_chat_service] = lambda: service
        app.dependency_overrides[get_request_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                body = {"answers": YES.model_dump(), "asked": ["first_cig", "no_smoke"]}
                selected = (await client.post("/api/v1/challenge-chat/select", json=body)).json()["data"]
                listed = (await client.get("/api/v1/challenge-recommendations")).json()["data"]["items"]
                started = await client.post(
                    "/api/v1/user-challenges",
                    json={"recommendation_ids": [selected["items"][0]["recommendation_id"]], "safety_confirmed": True},
                )
        finally:
            app.dependency_overrides.clear()

        assert selected["mode"] == "conversation"
        item, _ = selected["items"]
        card = next(row for row in listed if row["recommendation_id"] == item["recommendation_id"])
        # 전투 화면이 카드를 그릴 때 읽는 값은 대화 결과에도 모두 같은 값으로 있다
        shared = set(card) - {"proposed_goal", "action", "cooldown_choice", "exclude_until", "suppressed_until_manual"}
        assert {key: item[key] for key in shared} == {key: card[key] for key in shared}
        assert item["challenge_code"] == DELAY and item["reason"] == reason_for("first_cig", "yes")
        assert len(item["evidence_card_ids"]) == 1
        assert started.status_code == 201


class TestChallengeChatApi(TestCase):
    async def test_chat_endpoints_require_login_and_take_no_free_text(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            anonymous = await client.post("/api/v1/challenge-chat/select", json={})
            _, headers = await login(client, "chat-api@example.com")
            # 자유 대화 API 는 없다. 답은 선택지를 눌러서만 받는다
            free_text = await client.post(
                "/api/v1/challenge-chat", json={"messages": [{"role": "user", "content": "a"}]}, headers=headers
            )
            # 예측 전이라 규칙 추천(CHLG-01)과 같은 이유로 막힌다
            blocked = await client.post("/api/v1/challenge-chat/select", json={}, headers=headers)
        assert anonymous.status_code == 401
        assert free_text.status_code in (404, 405)
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
