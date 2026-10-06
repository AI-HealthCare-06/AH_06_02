import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.apis.v1.challenge_routers import get_recommendation_service
from app.core.utils.security import hash_password
from app.main import app
from app.models.health_records import HealthRecord
from app.models.users import User
from app.services.model_artifact import EXPERIMENTAL_STATUS, ArtifactLoader, parse_artifact
from app.services.recommendations import RecommendationService
from app.tests.d_fixtures import fake_artifact, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 7, 21, 0, tzinfo=KST)
REPO_ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "dango1234"


def _raw(status: Any) -> dict[str, Any]:
    """ai_worker/model_contract.py 형식. 숫자는 테스트용이다."""
    return {
        "status": status,
        "model_version": "test-model",
        "diseases": {
            "diabetes": {
                "global_importance": [{"factor_key": "smoking_current", "normalized_score": 40.0}],
                "positive_shap_p95_training_reference": {
                    "smoking_current": {"positive_shap_p95": 0.01, "threat_eligible": True}
                },
            }
        },
    }


def test_trained_artifact_is_not_experimental() -> None:
    artifact = parse_artifact(_raw("trained"))

    assert artifact is not None
    assert artifact.experimental is False


def test_experiment_only_artifact_is_experimental() -> None:
    artifact = parse_artifact(_raw("experiment_only_not_deployable"))

    assert artifact is not None
    assert artifact.experimental is True
    # 실험이어도 내용은 그대로 읽는다
    assert artifact.global_scores["diabetes"]["smoking_current"] == 40.0


@pytest.mark.parametrize("status", ["draft", "deployable", "TRAINED", "", None])
def test_other_statuses_are_still_rejected(status: Any) -> None:
    assert parse_artifact(_raw(status)) is None


def test_missing_status_is_rejected() -> None:
    raw = _raw("trained")
    del raw["status"]
    assert parse_artifact(raw) is None


def test_loader_reads_an_experimental_json_file(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(_raw(EXPERIMENTAL_STATUS)), encoding="utf-8")

    artifact = ArtifactLoader(path).load()

    assert artifact is not None
    assert artifact.experimental is True


def test_status_matches_what_run_baseline_writes() -> None:
    # 실험 산출물 표시가 바뀌면 여기서 먼저 알게 한다. run_baseline.py 는 sklearn 이 필요해 import 하지 않고 읽는다
    source = (REPO_ROOT / "scripts" / "model" / "run_baseline.py").read_text(encoding="utf-8")
    assert f'"status": "{EXPERIMENTAL_STATUS}"' in source


class TestRecommendWithExperimentalArtifact(TestCase):
    async def _diagnosed_smoker(self, email: str) -> User:
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        user = await User.create(
            email=email, password_hash=hash_password(PASSWORD), nickname="t", dm_diagnosed=True, htn_diagnosed=True
        )
        await make_target(user.id, ["smoking_current"])
        await HealthRecord.create(user_id=user.id, recorded_at=NOW, smoking_current=True)
        return user

    async def test_experimental_artifact_still_recommends(self) -> None:
        user = await self._diagnosed_smoker("exp-service@example.com")
        scores = {"diabetes": {"smoking_current": 40.0}}

        experimental = await RecommendationService(lambda: fake_artifact(scores, status=EXPERIMENTAL_STATUS)).generate(
            user, NOW
        )

        # 실험 아티팩트여도 추천은 막지 않는다. trained 와의 비교는 아래 API 테스트에서 한다
        assert [item.factor_key for item in experimental.items] == ["smoking_current"]
        assert float(experimental.items[0].factor_score) == 40.0
        assert experimental.model_experimental is True

    async def test_response_carries_the_experimental_flag(self) -> None:
        user = await self._diagnosed_smoker("exp-api@example.com")
        scores = {"diabetes": {"smoking_current": 40.0}}
        bodies = {}
        for status in ("trained", EXPERIMENTAL_STATUS):
            app.dependency_overrides[get_recommendation_service] = lambda status=status: RecommendationService(
                lambda: fake_artifact(scores, status=status)
            )
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    login = await client.post(
                        "/api/v1/auth/login", json={"email": "exp-api@example.com", "password": PASSWORD}
                    )
                    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
                    response = await client.post("/api/v1/challenge-recommendations/generate", headers=headers)
            finally:
                app.dependency_overrides.pop(get_recommendation_service, None)
            assert response.status_code == 200
            bodies[status] = response.json()["data"]

        assert bodies["trained"]["model_experimental"] is False
        assert bodies[EXPERIMENTAL_STATUS]["model_experimental"] is True
        assert bodies[EXPERIMENTAL_STATUS]["total"] == bodies["trained"]["total"] == 1
        assert user.dm_diagnosed is True
