"""질환별 실험 산출물 두 개를 서비스가 읽는 계약 형식 하나로 합친다.

    uv run python -m scripts.model.build_serving_artifact \\
        --diabetes data/experiment-2024-final-full/diabetes-sitting/<run>/artifact.json \\
        --hypertension data/experiment-2024-final-full/hypertension-sodium/<run>/artifact.json \\
        [--out data/model/artifact.json]

run_baseline.py 는 질환마다 global_importance 와 positive_shap_p95_training_reference 를 최상위에 둔다.
서비스(app/services/model_artifact.py)는 diseases.<질환> 아래에서 읽는다. 이 스크립트는 구조만 옮긴다.
숫자는 반올림·정규화·보정하지 않는다. status 는 입력보다 높게 올리지 않는다.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "model" / "artifact.json"

DISEASES = ("diabetes", "hypertension")
TRAINED = "trained"
EXPERIMENTAL = "experiment_only_not_deployable"
#: 낮은 쪽이 앞이다. 합친 결과는 입력 중 가장 낮은 상태를 따른다
STATUS_ORDER = (EXPERIMENTAL, TRAINED)
REQUIRED_KEYS = ("status", "model_version", "disease", "global_importance", "positive_shap_p95_training_reference")

#: predictions.model_version 은 VARCHAR(64) 다
MODEL_VERSION_MAX = 64
SERVING_VERSION_PREFIX = "serving-"
SERVING_VERSION_HASH_LEN = 16


class BuildError(ValueError):
    pass


def serving_model_version(source_versions: dict[str, str]) -> str:
    """두 원본 버전에서 짧은 합성 버전을 만든다.

    'serving-' + sha256("diabetes=<당뇨 버전>\\nhypertension=<고혈압 버전>") 앞 16자리. 항상 24자다.
    같은 입력이면 같은 버전이 나와 재현 가능하고(NFR-MODL-002), 원본 두 버전은 source_model_versions 에 남긴다.
    """
    key = "\n".join(f"{disease}={source_versions[disease]}" for disease in DISEASES)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:SERVING_VERSION_HASH_LEN]
    return f"{SERVING_VERSION_PREFIX}{digest}"


def combined_status(statuses: list[str]) -> str:
    unknown = sorted(set(statuses) - set(STATUS_ORDER))
    if unknown:
        raise BuildError(f"알 수 없는 status 입니다: {unknown}")
    return min(statuses, key=STATUS_ORDER.index)


def load_source(path: Path, expected_disease: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildError(f"{path} 를 읽을 수 없습니다: {exc}") from exc
    if not isinstance(raw, dict):
        raise BuildError(f"{path} 는 JSON 객체가 아닙니다")
    missing = [key for key in REQUIRED_KEYS if key not in raw]
    if missing:
        raise BuildError(f"{path} 에 필수 키가 없습니다: {missing}")
    if raw["disease"] not in DISEASES:
        raise BuildError(f"{path} 의 질환을 알 수 없습니다: {raw['disease']!r}")
    if raw["disease"] != expected_disease:
        raise BuildError(f"{path} 는 {raw['disease']} 산출물입니다. --{expected_disease} 자리에 넣었습니다")
    if not raw["global_importance"] or not raw["positive_shap_p95_training_reference"]:
        raise BuildError(f"{path} 의 global_importance 또는 positive_shap_p95_training_reference 가 비어 있습니다")
    return raw


def build(sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(sources) != set(DISEASES):
        raise BuildError(f"당뇨·고혈압 산출물이 하나씩 필요합니다: {sorted(sources)}")
    source_versions = {disease: str(sources[disease]["model_version"]) for disease in DISEASES}
    version = serving_model_version(source_versions)
    if len(version) > MODEL_VERSION_MAX:
        raise BuildError(f"합성 model_version 이 {MODEL_VERSION_MAX}자를 넘습니다: {version}")
    return {
        "status": combined_status([sources[disease]["status"] for disease in DISEASES]),
        "model_version": version,
        "source_model_versions": source_versions,
        "diseases": {
            disease: {
                # 값은 그대로 옮긴다
                "global_importance": sources[disease]["global_importance"],
                "positive_shap_p95_training_reference": sources[disease]["positive_shap_p95_training_reference"],
            }
            for disease in DISEASES
        },
    }


def run(diabetes: Path, hypertension: Path, out: Path) -> dict[str, Any]:
    """검증을 모두 통과해야 파일을 쓴다."""
    first = load_source(diabetes, "diabetes")
    second = load_source(hypertension, "hypertension")
    artifact = build({first["disease"]: first, second["disease"]: second})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="질환별 실험 산출물을 서비스 계약 형식 아티팩트로 합친다")
    parser.add_argument("--diabetes", type=Path, required=True, help="run_baseline.py 당뇨 artifact.json")
    parser.add_argument("--hypertension", type=Path, required=True, help="run_baseline.py 고혈압 artifact.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        artifact = run(args.diabetes, args.hypertension, args.out)
    except BuildError as exc:
        print(f"아티팩트 생성 실패: {exc}")
        return 1
    print(f"{args.out} 작성 · status={artifact['status']} · model_version={artifact['model_version']}")
    for disease, version in artifact["source_model_versions"].items():
        print(f"  {disease}: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
