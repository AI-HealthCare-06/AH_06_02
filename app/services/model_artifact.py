"""배포 모델 아티팩트 메타데이터 읽기.

global normalized_score 와 positive_shap_p95 는 DB 가 아니라 모델 아티팩트에 있다 (AGENTS.md 위협도 계산).
형식은 ai_worker/model_contract.py 의 ModelExplanationService 가 읽는 것과 같다.

    {"status": "trained", "model_version": "...",
     "diseases": {"diabetes": {"global_importance": [{"factor_key", "normalized_score", ...}],
                               "positive_shap_p95_training_reference": {factor: {"positive_shap_p95",
                                                                                  "threat_eligible", ...}}}}}

status 는 배포용 "trained" 와 실험용 "experiment_only_not_deployable" 만 받는다.
실험 아티팩트는 1단계 시연용으로 받되 experimental=True 로 표시해 응답까지 전한다.

app 이미지에는 ai_worker 가 들어가지 않아 import 하지 않고, 위협도 식만 같은 규칙으로 옮겼다.
두 구현이 어긋나지 않는지는 테스트가 확인한다.
"""

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import config

DEPLOYABLE_STATUS = "trained"
#: scripts/model/run_baseline.py 가 쓰는 실험 표시. 2024 자료로 후보를 고르고 같은 2024 로 성능을 쟀으므로
#: 독립 일반화 성능이 아니다 (docs/03_ai_data/experiment.md · submission-status.md)
EXPERIMENTAL_STATUS = "experiment_only_not_deployable"
#: 받는 status → 실험 모델 여부. 그 밖의 status 는 거부한다
ACCEPTED_STATUSES = {DEPLOYABLE_STATUS: False, EXPERIMENTAL_STATUS: True}


@dataclass(frozen=True)
class FactorReference:
    positive_shap_p95: float
    threat_eligible: bool


@dataclass(frozen=True)
class ModelArtifact:
    model_version: str
    #: disease -> factor_key -> global normalized_score (0~100)
    global_scores: dict[str, dict[str, float]]
    #: disease -> factor_key -> 개인 위협도 기준
    references: dict[str, dict[str, FactorReference]]
    #: 실험 아티팩트면 True. 이 값으로 낸 점수는 응답에 실험 모델임을 함께 싣는다
    experimental: bool


def parse_artifact(raw: Mapping[str, Any]) -> ModelArtifact | None:
    """배포용과 실험용 아티팩트를 받는다. 그 밖의 status 나 model_version 이 없으면 None."""
    status = raw.get("status")
    if status not in ACCEPTED_STATUSES or not raw.get("model_version"):
        return None
    global_scores: dict[str, dict[str, float]] = {}
    references: dict[str, dict[str, FactorReference]] = {}
    for disease, body in (raw.get("diseases") or {}).items():
        global_scores[disease] = {
            item["factor_key"]: float(item["normalized_score"]) for item in body.get("global_importance", [])
        }
        references[disease] = {
            factor: FactorReference(
                positive_shap_p95=float(item["positive_shap_p95"]),
                threat_eligible=bool(item["threat_eligible"]),
            )
            for factor, item in (body.get("positive_shap_p95_training_reference") or {}).items()
        }
    return ModelArtifact(
        model_version=str(raw["model_version"]),
        global_scores=global_scores,
        references=references,
        experimental=ACCEPTED_STATUSES[status],
    )


class ArtifactLoader:
    """파일에서 아티팩트를 읽는다. 없거나 배포 형식이 아니면 None."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or config.MODEL_ARTIFACT_PATH)

    def load(self) -> ModelArtifact | None:
        if not self.path.is_file():
            return None
        return parse_artifact(json.loads(self.path.read_text(encoding="utf-8")))


ArtifactSource = Callable[[], ModelArtifact | None]


def personal_threat_score(signed_shap: float, reference: FactorReference) -> int | None:
    """개인 위협도 0~100. ai_worker/model_contract.py threat_from_reference_p95 와 같은 규칙이다.

    positive_shap = max(signed SHAP, 0), score = min(100, positive_shap / P95 × 100), 반올림.
    threat_eligible 이 false 면 0 이다.
    """
    value = float(signed_shap)
    if not math.isfinite(value):
        return None
    if not reference.threat_eligible:
        return 0
    scale = reference.positive_shap_p95
    if not math.isfinite(scale) or scale < 0:
        return None
    if scale == 0:
        return 0
    return math.floor(100.0 * min(max(value, 0.0) / scale, 1.0) + 0.5)
