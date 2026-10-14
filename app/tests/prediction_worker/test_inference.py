"""실제 서빙 모델(experiment-refit/)로 전처리 계약과 SHAP 계산을 확인한다.

shap·pandas 가 있는 워커 환경에서만 돈다(CI 의 app 그룹에는 없다).
background 는 드라이브의 학습 기준 파일이 레포에 없어서, 계산 경로 확인용 행렬을 테스트 안에서만 만든다.
이 행렬로 낸 기여도 값은 artifact 의 P95 척도와 비교하지 않는다.
"""

import json
from pathlib import Path
from typing import Any

import pytest

shap = pytest.importorskip("shap")
pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from ai_worker.model_contract import FEATURE_FACTOR  # noqa: E402
from ai_worker.tasks.inference import (  # noqa: E402
    ModelUnavailableError,
    background_path,
    load_serving_models,
)

ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT / "data" / "experiment-refit"
SERVING = ROOT / "data" / "model" / "artifact.json"
pytestmark = pytest.mark.skipif(not (MODEL_DIR / "sitting-diabetes-42" / "model.joblib").is_file(), reason="모델 없음")

FEATURES: dict[str, Any] = {
    "age": 45,
    "sex": "M",
    "bmi": 27.4,
    "waist_cm": 92.0,
    "smoking_current": 1,
    "alcohol_frequency": 5,
    "alcohol_amount": 3,
    "walking_days": 1,
    "walking_minutes": 10,
    "strength_days": 0,
    "family_history_dm": 1,
    "family_history_htn": 0,
    "sitting_minutes": 720,
    "dining_out_freq": 2,
}


def test_missing_background_is_a_clear_error() -> None:
    if background_path(MODEL_DIR, "diabetes").is_file():
        pytest.skip("드라이브 background 가 이미 있다")
    with pytest.raises(ModelUnavailableError, match="background-diabetes.npy"):
        load_serving_models(SERVING, MODEL_DIR)


@pytest.fixture(scope="module")
def serving(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    """원본 실행 폴더를 링크하고 계산 확인용 background 를 둔 임시 모델 폴더."""
    import joblib

    folder = tmp_path_factory.mktemp("models")
    rng = np.random.default_rng(0)
    for run in ["sitting-diabetes-42", "sodium-hypertension-42"]:
        (folder / run).symlink_to(MODEL_DIR / run)
        disease = json.loads((MODEL_DIR / run / "artifact.json").read_text())["disease"]
        pipeline = joblib.load(MODEL_DIR / run / "model.joblib")
        transform = pipeline.named_steps["transform"]
        columns = list(transform.transformers_[0][2]) + list(transform.transformers_[1][2])
        rows = []
        for _ in range(100):
            row = dict(FEATURES)
            row.update(
                age=int(rng.integers(19, 80)),
                sex=str(rng.choice(["F", "M"])),
                bmi=float(rng.uniform(17, 35)),
                waist_cm=float(rng.uniform(60, 110)),
                alcohol_frequency=int(rng.integers(1, 7)),
                walking_days=int(rng.integers(0, 8)),
            )
            rows.append({key: row[key] for key in columns})
        np.save(background_path(folder, disease), transform.transform(pd.DataFrame(rows)).astype(np.float32))
    return load_serving_models(SERVING, folder)


def test_column_contract_matches_the_model_spec(serving) -> None:  # type: ignore[no-untyped-def]
    numeric = ["age", "bmi", "waist_cm", "walking_days", "walking_minutes", "strength_days"]
    categorical = [
        "sex",
        "smoking_current",
        "alcohol_frequency",
        "alcohol_amount",
        "family_history_dm",
        "family_history_htn",
    ]
    dm = serving.diseases["diabetes"]
    htn = serving.diseases["hypertension"]
    assert dm.columns == [*numeric, "sitting_minutes", *categorical]
    assert len(dm.encoded_order) == 27
    assert htn.columns == [*numeric, *categorical, "dining_out_freq"]
    assert len(htn.encoded_order) == 33
    encoder = dm.pipeline.named_steps["transform"].named_transformers_["cat"].named_steps["encode"]
    assert list(encoder.categories_[categorical.index("alcohol_amount")]) == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize("disease", ["diabetes", "hypertension"])
def test_probability_is_the_pipeline_output_and_shap_covers_every_factor(serving, disease: str) -> None:  # type: ignore[no-untyped-def]
    model = serving.diseases[disease]
    probability, items = model.predict(FEATURES)

    frame = pd.DataFrame([{key: FEATURES[key] for key in model.columns}])
    assert probability == pytest.approx(float(model.pipeline.predict_proba(frame)[0, 1]), abs=1e-12)
    factors = {item["factor_key"] for item in items}
    assert factors == {FEATURE_FACTOR[name] for name in model.columns}
    # 당뇨에는 좌식시간 요인만, 고혈압에는 나트륨 행동 요인만 있다
    assert ("sedentary_time_high" in factors) is (disease == "diabetes")
    assert ("sodium_behavior" in factors) is (disease == "hypertension")
    assert [item["rank"] for item in items] == list(range(1, len(items) + 1))


def test_explainer_is_built_once_per_disease(serving) -> None:  # type: ignore[no-untyped-def]
    model = serving.diseases["diabetes"]
    first = model.explainer
    model.predict(FEATURES)
    model.predict(FEATURES | {"bmi": 31.0})
    assert model.explainer is first


def test_string_category_is_rejected_instead_of_silently_ignored(serving) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="alcohol_frequency"):
        serving.diseases["diabetes"].predict(FEATURES | {"alcohol_frequency": "5"})
    with pytest.raises(ValueError, match="sex"):
        serving.diseases["diabetes"].predict(FEATURES | {"sex": 1})
