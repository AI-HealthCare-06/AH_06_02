"""예측 API 테스트 공용 준비물. 아티팩트 숫자와 입력값은 테스트용이다."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from httpx import AsyncClient

from app.apis.v1.prediction_routers import get_prediction_service
from app.core import config
from app.main import app
from app.models.health_records import HealthRecord, InputMode
from app.models.predictions import Prediction
from app.models.users import User
from app.services.model_artifact import EXPERIMENTAL_STATUS, ModelArtifact
from app.services.predictions import PredictionService
from app.tests.auth_apis.test_signup_api import signup_body
from app.tests.d_fixtures import fake_artifact

PASSWORD = "dango1234"

# 실제 서빙 모델과 같은 모양: 공통 12개 + 질환별 하나
CORE_FEATURES = [
    "age",
    "sex",
    "bmi",
    "waist_cm",
    "smoking_current",
    "alcohol_frequency",
    "alcohol_amount",
    "walking_days",
    "walking_minutes",
    "strength_days",
    "family_history_dm",
    "family_history_htn",
]
FEATURES = {"diabetes": [*CORE_FEATURES, "sitting_minutes"], "hypertension": [*CORE_FEATURES, "dining_out_freq"]}
ARTIFACT = fake_artifact(features=FEATURES, status=EXPERIMENTAL_STATUS)


async def login(client: AsyncClient, email: str, **overrides: object) -> tuple[User, dict[str, str]]:
    await client.post("/api/v1/auth/signup", json=signup_body(email=email, **overrides))
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return await User.get(email=email), {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


async def record(user_id: int, **overrides: Any) -> HealthRecord:
    values: dict[str, Any] = {
        "recorded_at": datetime.now(config.TIMEZONE),
        "input_mode": InputMode.SIMPLE,
        "weight_kg": Decimal("62.0"),
        "bmi": Decimal("23.1"),
        "waist_cm": Decimal("80.0"),
        "smoking_current": False,
        "alcohol_frequency": 3,
        "alcohol_amount": 2,
        "walking_days": 2,
        "walking_minutes": 20,
        "strength_days": 1,
        "sitting_minutes": 540,
        "family_history_dm": True,
        "family_history_htn": False,
        "dining_out_freq": 3,
    }
    return await HealthRecord.create(user_id=user_id, **(values | overrides))


@contextmanager
def serving(artifact: ModelArtifact | None = ARTIFACT) -> Iterator[None]:
    app.dependency_overrides[get_prediction_service] = lambda: PredictionService(lambda: artifact)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_prediction_service, None)


def snapshot(prediction: Prediction) -> dict[str, Any]:
    """접수 시점 입력 스냅샷. 모델 필드 타입이 dict[str, object] 라 테스트에서 읽기 쉽게 바꾼다."""
    assert prediction.input_snapshot is not None
    return cast(dict[str, Any], prediction.input_snapshot)
