"""질환 모델 추론과 SHAP 기여도. 학습(scripts/model/run_baseline.py explain)과 같은 기준으로 계산한다.

- 전처리: model.joblib 은 Pipeline([transform, forest])이고 transform 이 결측 보정·인코딩을 모두 들고 있다.
  여기서는 원본 코드 그대로의 DataFrame 만 만든다. 질환마다 입력 컬럼이 달라 DataFrame 도 따로 만든다.
- SHAP: 고정 background(.npy, transform 을 통과한 100행)로 explainer 를 질환마다 한 번만 만든다.
  background 를 새로 뽑으면 artifact 의 positive_shap_p95_training_reference 와 척도가 어긋난다.
- shap==0.50.0 은 프로젝트 lock 에 넣을 수 없어(pyproject.toml model 그룹 주석) 워커 이미지에서만 설치한다.
  numpy·pandas·joblib·shap 은 함수 안에서 불러온다. 저장 로직(predict.py)과 그 테스트는 app 의존성만으로 돈다.
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_worker.model_contract import FEATURE_FACTOR, group_shap, rank_contributions

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

MODEL_FILE = "model.joblib"
ARTIFACT_FILE = "artifact.json"
#: run_baseline.py explain() 의 background 행 수
BACKGROUND_ROWS = 100
#: run_baseline.py explain() 의 가산성 허용 오차
ADDITIVITY_TOLERANCE = 1e-2
#: 문자열로 넘기는 유일한 범주. 나머지 범주는 문자열이면 handle_unknown='ignore' 로 조용히 0 이 된다
STRING_FEATURES = frozenset({"sex"})


class ModelUnavailableError(RuntimeError):
    """모델·background 파일이 없거나 학습 산출물과 맞지 않는다. 재시도해도 같은 결과다."""


def background_path(model_dir: Path, disease: str) -> Path:
    return model_dir / f"background-{disease}.npy"


@dataclass(frozen=True)
class DiseaseModel:
    disease: str
    model_version: str
    train_years: list[int]
    pipeline: Any
    explainer: Any
    #: DataFrame 컬럼 순서. transform 의 수치 → 범주 순서다
    columns: list[str]
    #: 인코딩 후 열마다 원래 입력 이름. SHAP 을 요인으로 합칠 때 쓴다
    encoded_order: list[str]

    def frame(self, features: Mapping[str, Any]) -> "pd.DataFrame":
        """원본 코드 그대로 한 행. bool·int 는 그대로, sex 만 문자열이다."""
        import pandas as pd

        row: dict[str, Any] = {}
        for name in self.columns:
            value = features.get(name)
            if value is None:
                # 접수(PRED-01)에서 막는 조건이라 여기 오면 입력이 잘못된 것이다
                raise ValueError(f"{self.disease} 모델 입력이 없다: {name}")
            if isinstance(value, str) != (name in STRING_FEATURES):
                raise ValueError(f"{self.disease} 모델 입력 타입이 맞지 않다: {name}")
            row[name] = value
        return pd.DataFrame([row], columns=self.columns)

    def predict(self, features: Mapping[str, Any]) -> tuple[float, list[dict[str, Any]]]:
        """양성 확률과 전체 factor 기여도(0 포함, rank 포함)."""
        import numpy as np

        frame = self.frame(features)
        forest = self.pipeline.named_steps["forest"]
        positive = list(forest.classes_).index(1)
        probability = float(self.pipeline.predict_proba(frame)[0, positive])
        encoded = self.pipeline.named_steps["transform"].transform(frame).astype(np.float32)
        values = np.asarray(self.explainer.shap_values(encoded, check_additivity=False))
        if values.ndim != 3 or values.shape[1:] != (len(self.encoded_order), 2):
            raise ValueError(f"SHAP 결과 모양이 예상과 다르다: {values.shape}")
        shap_row = values[0, :, positive]
        base = float(np.asarray(self.explainer.expected_value)[positive])
        error = abs(base + float(shap_row.sum()) - probability)
        if not math.isfinite(error) or error > ADDITIVITY_TOLERANCE:
            raise ValueError(f"확률 공간 SHAP 가산성 실패: {error:.6g}")
        mapping = {str(index): FEATURE_FACTOR[name] for index, name in enumerate(self.encoded_order)}
        grouped = group_shap({str(index): float(value) for index, value in enumerate(shap_row)}, mapping)
        return probability, rank_contributions(grouped)


def column_plan(transform: Any) -> tuple[list[str], list[str]]:
    """입력 컬럼 순서와 인코딩 후 순서. scripts/model/inspect_serving_model.py column_plan 과 같다."""
    numeric = list(transform.transformers_[0][2])
    categorical = list(transform.transformers_[1][2])
    encoder = transform.named_transformers_["cat"].named_steps["encode"]
    encoded_order = numeric.copy()
    for key, categories in zip(categorical, encoder.categories_, strict=True):
        encoded_order.extend([key] * len(categories))
    return numeric + categorical, encoded_order


def load_background(path: Path, width: int) -> "np.ndarray":
    import numpy as np

    if not path.is_file():
        raise ModelUnavailableError(
            f"SHAP background 파일이 없다: {path}. 모델 폴더(드라이브)의 {path.name} 를 받아 이 경로에 둬야 한다. "
            "새로 뽑으면 artifact 의 positive_shap_p95 척도와 어긋나므로 만들어 쓰지 않는다"
        )
    background = np.load(path, allow_pickle=False)
    if background.shape != (BACKGROUND_ROWS, width):
        raise ModelUnavailableError(f"{path.name} 모양이 ({BACKGROUND_ROWS}, {width}) 가 아니다: {background.shape}")
    return background.astype(np.float32)


def load_disease_model(run_dir: Path, model_dir: Path) -> DiseaseModel:
    import joblib
    import shap  # 워커 이미지에만 있다

    artifact = json.loads((run_dir / ARTIFACT_FILE).read_text(encoding="utf-8"))
    disease = str(artifact["disease"])
    pipeline = joblib.load(run_dir / MODEL_FILE)
    if "transform" not in pipeline.named_steps or "forest" not in pipeline.named_steps:
        raise ModelUnavailableError(f"{run_dir.name}: transform·forest 파이프라인이 아니다")
    columns, encoded_order = column_plan(pipeline.named_steps["transform"])
    if sorted(columns) != sorted(artifact["features"]):
        raise ModelUnavailableError(f"{run_dir.name}: artifact features 와 model.joblib 입력이 다르다")
    background = load_background(background_path(model_dir, disease), len(encoded_order))
    explainer = shap.TreeExplainer(
        pipeline.named_steps["forest"],
        data=background,
        feature_perturbation="interventional",
        model_output="probability",
    )
    train = artifact["split"]["train"]
    return DiseaseModel(
        disease=disease,
        model_version=str(artifact["model_version"]),
        train_years=sorted([train] if isinstance(train, int) else train),
        pipeline=pipeline,
        explainer=explainer,
        columns=columns,
        encoded_order=encoded_order,
    )


@dataclass(frozen=True)
class ServingModels:
    """서빙 artifact(data/model/artifact.json) 하나와 그 원본 질환 모델들."""

    model_version: str
    diseases: dict[str, DiseaseModel]


def load_serving_models(serving_artifact: Path, model_dir: Path) -> ServingModels:
    """서빙 artifact 가 가리키는 원본 버전·학습 연도와 model_dir 의 실행 산출물이 같은지 확인하고 읽는다."""
    if not serving_artifact.is_file():
        raise ModelUnavailableError(f"서빙 artifact 가 없다: {serving_artifact}")
    serving = json.loads(serving_artifact.read_text(encoding="utf-8"))
    sources: dict[str, str] = serving.get("source_model_versions") or {}
    years: dict[str, list[int]] = serving.get("source_train_years") or {}
    runs: dict[tuple[str, str], Path] = {}
    for artifact_path in sorted(model_dir.glob(f"*/{ARTIFACT_FILE}")):
        meta = json.loads(artifact_path.read_text(encoding="utf-8"))
        runs[(str(meta.get("disease")), str(meta.get("model_version")))] = artifact_path.parent
    diseases: dict[str, DiseaseModel] = {}
    for disease, body in (serving.get("diseases") or {}).items():
        run_dir = runs.get((disease, str(sources.get(disease))))
        if run_dir is None:
            raise ModelUnavailableError(f"{model_dir} 에 {disease} 원본 모델 {sources.get(disease)!r} 이 없다")
        model = load_disease_model(run_dir, model_dir)
        if sorted(model.columns) != sorted(body.get("features") or []):
            raise ModelUnavailableError(f"{disease}: 서빙 artifact 입력 목록과 원본 모델 입력이 다르다")
        if model.train_years != sorted(years.get(disease) or []):
            raise ModelUnavailableError(f"{disease}: 서빙 artifact 학습 연도와 원본 모델 학습 연도가 다르다")
        diseases[disease] = model
    if not diseases:
        raise ModelUnavailableError("서빙 artifact 에 질환 모델이 없다")
    return ServingModels(model_version=str(serving["model_version"]), diseases=diseases)
