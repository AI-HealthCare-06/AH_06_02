"""추천은 최신 간편·정밀 입력의 예측만 사용한다. daily 기록은 평가 기준을 바꾸지 않는다."""

from datetime import datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.apis.v1.challenge_routers import get_recommendation_service
from app.core import config
from app.main import app
from app.models.challenges import ChallengeRecommendation, DiseaseScope, Monster, UserMonster
from app.models.health_records import HealthRecord, InputMode
from app.models.predictions import ContributionDirection, Disease, Prediction, PredictionContribution, PredictionStatus
from app.models.users import User
from app.services.model_artifact import ModelArtifact
from app.services.recommendations import RecommendationService
from app.tests.auth_apis.test_signup_api import signup_body
from app.tests.d_fixtures import fake_artifact, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges


class TestPredictionFreshness(TestCase):
    async def _prepare(self, client: AsyncClient) -> tuple[User, dict[str, str], HealthRecord, ModelArtifact]:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        email = "fresh-prediction@example.com"
        await client.post("/api/v1/auth/signup", json=signup_body(email=email, htn_diagnosed=True))
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": "dango1234"})
        user = await User.get(email=email)
        headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
        await make_target(user.id, ["smoking_current"], scope=DiseaseScope.DIABETES)
        record = await HealthRecord.create(
            user_id=user.id, recorded_at=datetime.now(config.TIMEZONE), smoking_current=True
        )
        artifact = fake_artifact(p95={"diabetes": {"smoking_current": 0.01}})
        return user, headers, record, artifact

    async def _done(self, user: User, record: HealthRecord, artifact: ModelArtifact) -> Prediction:
        prediction = await Prediction.create(
            user_id=user.id,
            health_record_id=record.id,
            job_id=f"job-fresh-{record.id}",
            status=PredictionStatus.DONE,
            model_version=artifact.model_version,
            dm_probability=Decimal("0.1"),
            predicted_at=record.recorded_at,
        )
        await PredictionContribution.create(
            prediction_id=prediction.id,
            disease=Disease.DIABETES,
            factor_key="smoking_current",
            contribution=Decimal("0.005"),
            direction=ContributionDirection.INCREASE,
            rank=1,
        )
        return prediction

    async def test_new_health_record_cannot_use_previous_prediction(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, old, artifact = await self._prepare(client)
            await self._done(user, old, artifact)
            await HealthRecord.create(
                user_id=user.id, recorded_at=old.recorded_at + timedelta(seconds=1), smoking_current=False
            )
            app.dependency_overrides[get_recommendation_service] = lambda: RecommendationService(lambda: artifact)
            try:
                response = await client.post("/api/v1/challenge-recommendations/generate", headers=headers)
            finally:
                app.dependency_overrides.pop(get_recommendation_service, None)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PRED_NOT_FOUND"
        assert await ChallengeRecommendation.filter(user_id=user.id).count() == 0

    async def test_factor_scores_reject_previous_record_prediction(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, _, old, artifact = await self._prepare(client)
        await self._done(user, old, artifact)
        await HealthRecord.create(
            user_id=user.id, recorded_at=old.recorded_at + timedelta(seconds=1), smoking_current=False
        )
        target = await UserMonster.get(user_id=user.id)
        monster = await Monster.get(id=target.monster_id)

        scores, missing = await RecommendationService(lambda: artifact)._factor_scores(user, monster, artifact)

        assert scores == {}
        assert missing is True

    async def test_daily_record_does_not_replace_prediction_input(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, _, record, artifact = await self._prepare(client)
        await self._done(user, record, artifact)
        await HealthRecord.create(
            user_id=user.id,
            recorded_at=record.recorded_at + timedelta(seconds=1),
            input_mode=InputMode.DAILY,
            weight_kg=Decimal("65"),
        )

        generated = await RecommendationService(lambda: artifact).generate(user)

        assert len(generated.items) == 1
        assert generated.items[0].factor_score == Decimal("50")

    async def test_late_previous_record_result_does_not_hide_current_result(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, _, old, artifact = await self._prepare(client)
        late = await self._done(user, old, artifact)
        current = await HealthRecord.create(
            user_id=user.id, recorded_at=old.recorded_at + timedelta(seconds=1), smoking_current=True
        )
        await self._done(user, current, artifact)
        await Prediction.filter(id=late.id).update(predicted_at=current.recorded_at + timedelta(seconds=1))
        await PredictionContribution.filter(prediction_id=late.id).update(contribution=Decimal("0.009"))

        generated = await RecommendationService(lambda: artifact).generate(user)

        assert len(generated.items) == 1
        assert generated.items[0].factor_score == Decimal("50")

    async def test_different_version_does_not_hide_matching_current_result(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, _, record, artifact = await self._prepare(client)
        await self._done(user, record, artifact)
        await Prediction.create(
            user_id=user.id,
            health_record_id=record.id,
            job_id="job-other-version",
            model_version="previous-model",
            status=PredictionStatus.DONE,
            dm_probability=Decimal("0.2"),
            predicted_at=record.recorded_at + timedelta(seconds=1),
        )

        generated = await RecommendationService(lambda: artifact).generate(user)

        assert len(generated.items) == 1
        assert generated.items[0].factor_score == Decimal("50")

    async def test_medication_without_diagnosis_uses_global_recommendation(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, _, _ = await self._prepare(client)
            await User.filter(id=user.id).update(dm_medication=True)
            artifact = fake_artifact({"diabetes": {"smoking_current": 40.0}})
            app.dependency_overrides[get_recommendation_service] = lambda: RecommendationService(lambda: artifact)
            try:
                response = await client.post("/api/v1/challenge-recommendations/generate", headers=headers)
            finally:
                app.dependency_overrides.pop(get_recommendation_service, None)

        assert response.status_code == 200
        assert response.json()["data"]["items"][0]["factor_score"] == 40.0
