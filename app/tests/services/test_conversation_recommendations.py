"""합성 승인 fixture로 저장·실패·기존 시작 계약을 확인한다. 실제 LLM 평가는 아니다."""

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tortoise.contrib.test import TestCase

from app.core import config
from app.models.challenges import Challenge, ChallengeRecommendation, RecommendationSourceType, UserChallenge
from app.models.health_records import HealthRecord
from app.models.predictions import Disease, Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.services.challenges import ChallengeCoreService
from app.services.conversation_recommendations import ConversationRecommendationService
from app.services.rag_cards import SituationAnswers, load_cards
from app.services.recommendations import RecommendationService
from app.tests.d_fixtures import fake_artifact, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

CORPUS = Path(__file__).resolve().parents[3] / "docs/01_planning/chatbot/cards-draft-20261012.json"


class FixtureProvider:
    model_version = "fixture-model"

    def __init__(self, callback=None, bad=False):
        self.callback, self.bad, self.calls = callback, bad, 0

    async def select(self, cards, answers):
        self.calls += 1
        if self.callback:
            await self.callback()
        return {
            "selections": [
                {"challenge_code": "INVALID" if self.bad else "CH_WALK_AFTER_MEAL", "evidence_card_id": "C01"}
            ]
        }


class TestConversationRecommendation(TestCase):
    async def prepare(self):
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        user = await User.create(
            email="rag-fixture@example.com",
            password_hash="x",
            nickname="검증",
            dm_diagnosed=False,
            htn_diagnosed=False,
            dm_medication=False,
            htn_medication=False,
        )
        now = datetime.now(config.TIMEZONE)
        record = await HealthRecord.create(user_id=user.id, recorded_at=now)
        prediction = await Prediction.create(
            user_id=user.id,
            health_record_id=record.id,
            job_id="rag-fixture",
            model_version="test-model",
            status=PredictionStatus.DONE,
            dm_probability=Decimal("0.3"),
            htn_probability=Decimal("0.2"),
            predicted_at=now,
        )
        for disease in Disease:
            await PredictionContribution.create(
                prediction_id=prediction.id,
                disease=disease,
                factor_key="physical_activity_low",
                contribution=Decimal("0.01"),
                direction="increase",
                rank=1,
            )
        await make_target(user.id, ["physical_activity_low"])
        artifact = fake_artifact(
            p95={"diabetes": {"physical_activity_low": 0.01}, "hypertension": {"physical_activity_low": 0.01}}
        )
        rules = RecommendationService(lambda: artifact)
        generated = await rules.generate(user)
        cards = [
            card.model_copy(update={"status": "approved", "approved_by": "테스트 fixture"})
            for card in load_cards(CORPUS)
        ]
        return user, rules, generated, cards

    async def test_conversation_stores_trace_without_creating_or_changing_missions(self):
        user, rules, generated, cards = await self.prepare()
        provider = FixtureProvider()
        service = ConversationRecommendationService(rules, cards, provider, enabled=True)
        count = await ChallengeRecommendation.all().count()
        result = await service.personalize(
            user,
            generated,
            query="점심 식후",
            answers=SituationAnswers(meal_walk="both", transit="no", stairs="no"),
            asked=["meal_walk"],
        )
        assert result.mode == "conversation"
        row = result.recommendations.items[0]
        assert row.source_type == RecommendationSourceType.PREDICTION_PERSONAL
        assert row.llm_model_version == "fixture-model" and row.evidence_card_ids == ["C01"]
        assert row.proposed_goal is None
        assert await UserChallenge.all().count() == 0
        assert "query" not in row.conversation_snapshot
        assert await ChallengeRecommendation.all().count() == count
        again = await service.personalize(
            user,
            generated,
            query="점심 식후",
            answers=SituationAnswers(meal_walk="both", transit="no", stairs="no"),
            asked=["meal_walk"],
        )
        assert again.mode == "conversation" and again.recommendations.items[0].id == row.id
        assert again.recommendations.items[0].source_type == RecommendationSourceType.PREDICTION_PERSONAL
        changed = await service.personalize(
            user,
            generated,
            query="점심 식후",
            answers=SituationAnswers(meal_walk="both_indoor", transit="no", stairs="no"),
            asked=["meal_walk"],
        )
        assert changed.mode == "hold"
        assert await ChallengeRecommendation.all().count() == count
        [mission] = await ChallengeCoreService().start_from_recommendations(
            user_id=user.id, recommendation_ids=[row.id]
        )
        assert mission.target_value_snapshot == Decimal("10") and mission.daily_target_count_snapshot == 2

    async def test_new_health_record_during_model_call_prevents_stale_save(self):
        user, rules, generated, cards = await self.prepare()

        async def change_record():
            await HealthRecord.create(user_id=user.id, recorded_at=datetime.now(config.TIMEZONE) + timedelta(minutes=1))

        result = await ConversationRecommendationService(
            rules, cards, FixtureProvider(change_record), enabled=True
        ).personalize(
            user,
            generated,
            query="점심 식후",
            answers=SituationAnswers(meal_walk="both", transit="no", stairs="no"),
            asked=["meal_walk"],
        )
        assert result.mode == "hold" and result.recommendations.items == []
        assert await ChallengeRecommendation.filter(conversation_snapshot__isnull=False).count() == 0

    async def test_master_goal_change_during_model_call_prevents_old_goal_advice(self):
        user, rules, generated, cards = await self.prepare()

        async def change_master():
            await Challenge.filter(code="CH_WALK_AFTER_MEAL").update(target_value=Decimal("5"))

        result = await ConversationRecommendationService(
            rules, cards, FixtureProvider(change_master), enabled=True
        ).personalize(
            user,
            generated,
            query="점심 식후",
            answers=SituationAnswers(meal_walk="both", transit="no", stairs="no"),
            asked=["meal_walk"],
        )
        assert result.mode == "hold"
        assert await ChallengeRecommendation.filter(conversation_snapshot__isnull=False).count() == 0

    async def test_changed_master_before_generation_does_not_use_old_fixed_questions(self):
        user, rules, _, cards = await self.prepare()
        await Challenge.filter(code="CH_WALK_AFTER_MEAL").update(target_value=Decimal("5"))
        generated = await rules.generate(user)
        provider = FixtureProvider()
        result = await ConversationRecommendationService(rules, cards, provider, enabled=True).personalize(
            user, generated, query="점심 식후", answers=SituationAnswers(), asked=[]
        )
        assert result.mode == "hold" and result.questions == []
        assert provider.calls == 0

    async def test_invalid_llm_output_keeps_rules_and_draft_corpus_never_calls_model(self):
        user, rules, generated, cards = await self.prepare()
        result = await ConversationRecommendationService(
            rules, cards, FixtureProvider(bad=True), enabled=True
        ).personalize(
            user,
            generated,
            query="점심 식후",
            answers=SituationAnswers(meal_walk="both", transit="no", stairs="no"),
            asked=["meal_walk"],
        )
        assert result.mode == "rules"
        assert await ChallengeRecommendation.filter(conversation_snapshot__isnull=False).count() == 0
        provider = FixtureProvider()
        await ConversationRecommendationService(rules, load_cards(CORPUS), provider, enabled=True).personalize(
            user,
            generated,
            query="점심 식후",
            answers=SituationAnswers(meal_walk="both", transit="no", stairs="no"),
            asked=["meal_walk"],
        )
        assert provider.calls == 0
