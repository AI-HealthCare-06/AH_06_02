import json
import logging
from pathlib import Path
from typing import Any

import pytest

from app.services.model_artifact import parse_artifact
from scripts.model.build_serving_artifact import MODEL_VERSION_MAX, main, serving_model_version

# run_baseline.py 가 실제로 쓰는 버전 문자열 길이 (고혈압 39자)
DM_VERSION = "knhanes-ix-diabetes-base_sitting-s42"
HTN_VERSION = "knhanes-ix-hypertension-base_sodium-s42"


def baseline_artifact(disease: str, version: str, status: str = "experiment_only_not_deployable") -> dict[str, Any]:
    """run_baseline.py 의 artifact.json 과 같은 키 구조. 숫자는 테스트용이다."""
    return {
        "status": status,
        "model_version": version,
        "disease": disease,
        "features": ["age", "smoking_current"],
        "seed": 42,
        "split": {"train": 2022, "validation": 2023, "test": 2024},
        "test_evaluated": True,
        "validation_metrics": {"auroc": 0.5},
        "test_metrics": {"auroc": 0.5},
        "global_importance": [
            {
                "factor_key": "age",
                "importance": 0.012345678901234,
                "normalized_score": 100.0,
                "modifiable": False,
                "rank": 1,
            },
            {
                "factor_key": "smoking_current",
                "importance": 0.001234567890123,
                "normalized_score": 10.000000000000002,
                "modifiable": True,
                "rank": 2,
            },
        ],
        "positive_shap_p95_training_reference": {
            "age": {"positive_shap_p95": 0.028688442, "positive_n": 2437, "reference_n": 4418, "threat_eligible": True},
            "smoking_current": {
                "positive_shap_p95": 0.012888590123456,
                "positive_n": 707,
                "reference_n": 4418,
                "threat_eligible": True,
            },
        },
        "shap_additivity_max_abs_error": {"tolerance": 0.01},
    }


def _write(tmp_path: Path, name: str, body: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _build(tmp_path: Path, dm: dict[str, Any], htn: dict[str, Any]) -> tuple[int, Path]:
    out = tmp_path / "out" / "artifact.json"
    code = main(
        [
            "--diabetes",
            str(_write(tmp_path, "dm.json", dm)),
            "--hypertension",
            str(_write(tmp_path, "htn.json", htn)),
            "--out",
            str(out),
        ]
    )
    return code, out


# ---------------------------------------------------------------- 1. 구조가 깨진 아티팩트 거부


def test_run_baseline_file_as_is_is_rejected_with_a_reason(caplog: pytest.LogCaptureFixture) -> None:
    # 내일 실제로 벌어질 수 있는 상황: 질환별 산출물을 합치지 않고 그대로 넣는다
    with caplog.at_level(logging.WARNING):
        assert parse_artifact(baseline_artifact("diabetes", DM_VERSION)) is None

    assert "diseases 가 없거나 비어 있다" in caplog.text


@pytest.mark.parametrize(
    ("diseases", "reason"),
    [
        ({}, "diseases 가 없거나 비어 있다"),
        (
            {"diabetes": {"global_importance": [], "positive_shap_p95_training_reference": {"age": {}}}},
            "diabetes 의 global_importance 가 비어 있다",
        ),
        (
            {
                "diabetes": {
                    "global_importance": [{"factor_key": "age", "normalized_score": 100.0}],
                    "positive_shap_p95_training_reference": {},
                }
            },
            "diabetes 의 positive_shap_p95_training_reference 가 비어 있다",
        ),
        (
            {
                "diabetes": {
                    "global_importance": [{"factor_key": "age"}],
                    "positive_shap_p95_training_reference": {
                        "age": {"positive_shap_p95": 0.03, "threat_eligible": True}
                    },
                }
            },
            "항목 형식이 맞지 않다",
        ),
    ],
)
def test_broken_structures_are_rejected(
    diseases: dict[str, Any], reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    raw = {"status": "trained", "model_version": "v", "diseases": diseases}
    with caplog.at_level(logging.WARNING):
        assert parse_artifact(raw) is None

    assert reason in caplog.text


# ---------------------------------------------------------------- 2. 계약 형식으로 합치기


def test_build_moves_structure_and_passes_parse(tmp_path: Path) -> None:
    dm, htn = baseline_artifact("diabetes", DM_VERSION), baseline_artifact("hypertension", HTN_VERSION)

    code, out = _build(tmp_path, dm, htn)

    assert code == 0
    built = json.loads(out.read_text(encoding="utf-8"))
    # 숫자를 포함해 원본 그대로 옮겼다
    for disease, source in (("diabetes", dm), ("hypertension", htn)):
        assert built["diseases"][disease]["global_importance"] == source["global_importance"]
        assert (
            built["diseases"][disease]["positive_shap_p95_training_reference"]
            == source["positive_shap_p95_training_reference"]
        )
    assert built["source_model_versions"] == {"diabetes": DM_VERSION, "hypertension": HTN_VERSION}

    artifact = parse_artifact(built)
    assert artifact is not None
    assert artifact.experimental is True
    assert artifact.model_version == built["model_version"]
    assert artifact.global_scores["diabetes"]["smoking_current"] == 10.000000000000002
    assert artifact.references["hypertension"]["smoking_current"].positive_shap_p95 == 0.012888590123456


@pytest.mark.parametrize(
    ("dm_status", "htn_status", "expected"),
    [
        ("trained", "trained", "trained"),
        ("trained", "experiment_only_not_deployable", "experiment_only_not_deployable"),
        ("experiment_only_not_deployable", "trained", "experiment_only_not_deployable"),
    ],
)
def test_status_never_goes_above_the_inputs(tmp_path: Path, dm_status: str, htn_status: str, expected: str) -> None:
    code, out = _build(
        tmp_path,
        baseline_artifact("diabetes", DM_VERSION, dm_status),
        baseline_artifact("hypertension", HTN_VERSION, htn_status),
    )

    assert code == 0
    built = json.loads(out.read_text(encoding="utf-8"))
    assert built["status"] == expected
    artifact = parse_artifact(built)
    assert artifact is not None
    assert artifact.experimental is (expected != "trained")


def test_serving_version_fits_predictions_column_and_is_deterministic() -> None:
    real = serving_model_version({"diabetes": DM_VERSION, "hypertension": HTN_VERSION})
    huge = serving_model_version({"diabetes": "d" * 500, "hypertension": "h" * 500})

    assert len(DM_VERSION) + len(HTN_VERSION) > MODEL_VERSION_MAX  # 이어 붙이면 넘친다
    assert len(real) <= MODEL_VERSION_MAX
    assert len(huge) <= MODEL_VERSION_MAX
    assert real == serving_model_version({"diabetes": DM_VERSION, "hypertension": HTN_VERSION})
    assert real != serving_model_version({"diabetes": HTN_VERSION, "hypertension": DM_VERSION})


@pytest.mark.parametrize(
    "case",
    ["same_disease_twice", "unknown_disease", "missing_key", "unknown_status", "empty_importance"],
)
def test_bad_inputs_exit_1_without_writing(tmp_path: Path, case: str) -> None:
    dm, htn = baseline_artifact("diabetes", DM_VERSION), baseline_artifact("hypertension", HTN_VERSION)
    if case == "same_disease_twice":
        htn = baseline_artifact("diabetes", DM_VERSION)
    elif case == "unknown_disease":
        htn["disease"] = "obesity"
    elif case == "missing_key":
        del htn["positive_shap_p95_training_reference"]
    elif case == "unknown_status":
        htn["status"] = "draft"
    elif case == "empty_importance":
        dm["global_importance"] = []

    code, out = _build(tmp_path, dm, htn)

    assert code == 1
    assert not out.exists()
