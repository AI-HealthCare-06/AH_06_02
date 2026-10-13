"""서빙 모델 바이너리에서 전처리 계약과 SHAP background 를 뽑는다.

큐·워커가 model.joblib 을 그대로 쓰려면 두 가지가 필요하다.

1. 전처리 계약 - 어떤 컬럼을, 어떤 순서로, 어떤 코드로 넣어야 하는지.
   model.joblib 안의 ColumnTransformer 가 이미 전처리 전부를 들고 있으므로
   워커가 결측 보정·인코딩을 다시 구현하면 안 된다. 원본 코드 그대로 담은
   DataFrame 을 model.predict_proba 에 넘기면 된다. 이 모드는 바이너리만 있으면 돈다.

       uv run --group model python scripts/model/inspect_serving_model.py \
           --model data/serving/sitting-diabetes-42/model.joblib \
           --artifact data/model/artifact.json --disease diabetes

2. SHAP background - shap.TreeExplainer 의 interventional 기준점.
   run_baseline.py 의 explain() 과 같은 규칙으로 학습 구간에서 100행을 뽑아
   인코딩한 행렬이다. canonical.csv 가 있어야 만들 수 있고, 한 번 만들어
   파일로 고정한 뒤 워커가 매번 그 파일을 읽어야 한다. 매 요청마다 새로 뽑으면
   같은 입력에 다른 기여도가 나오고 artifact.json 의
   positive_shap_p95_training_reference 와 척도가 어긋난다.

       uv run --group model --with 'shap==0.50.0' python scripts/model/inspect_serving_model.py \
           --model data/serving/sitting-diabetes-42/model.joblib \
           --disease diabetes --canonical data/canonical.csv \
           --train-years 2022 2023 --emit-background data/serving/background-diabetes.npy

   만들어진 .npy 는 KNHANES 개인 단위 행을 인코딩한 것이다. 보안서약 대상이라
   Git·Slack 에 올리지 않는다. 모델 바이너리와 같은 경로(드라이브)로만 주고받는다.
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np

#: run_baseline.py 가 쓴 난수 시드. background 표본을 같게 재현하려면 바꾸면 안 된다
REFERENCE_SEED = 42
#: explain() 이 background 로 쓰는 행 수
BACKGROUND_ROWS = 100
#: explain() 이 학습 구간에서 먼저 잘라내는 표본 크기(run_one 의 reference_size 기본값)
REFERENCE_SIZE = 256


def load_model(path: Path):
    model = joblib.load(path)
    if "transform" not in model.named_steps or "forest" not in model.named_steps:
        raise SystemExit(f"{path} 는 transform·forest 단계를 가진 파이프라인이 아닙니다")
    return model


def column_plan(transform):
    """fitted ColumnTransformer 에서 입력 컬럼과 인코딩 결과를 읽는다."""
    numeric = list(transform.transformers_[0][2])
    categorical = list(transform.transformers_[1][2])
    encoder = transform.named_transformers_["cat"].named_steps["encode"]
    categories = {key: list(values) for key, values in zip(categorical, encoder.categories_, strict=True)}
    # SHAP 기여도를 요인별로 합칠 때 쓰는 인코딩 후 순서. 수치가 먼저고 범주는 카테고리 수만큼 반복된다
    encoded_order = numeric.copy()
    for key in categorical:
        encoded_order.extend([key] * len(categories[key]))
    return numeric, categorical, categories, encoded_order


def describe(model, artifact_path: Path | None, disease: str | None) -> None:
    transform = model.named_steps["transform"]
    forest = model.named_steps["forest"]
    numeric, categorical, categories, encoded_order = column_plan(transform)

    print("## 파이프라인")
    print(f"- 단계: {' -> '.join(model.named_steps)}")
    settings = f"n_estimators={forest.n_estimators} max_depth={forest.max_depth}"
    print(f"- 분류기: {type(forest).__name__} {settings} min_samples_leaf={forest.min_samples_leaf}")
    print(f"- 클래스: {list(forest.classes_)} (양성 확률은 predict_proba(...)[:, 1])")

    print("\n## 입력 DataFrame 컬럼 (이 순서 그대로)")
    for key in numeric + categorical:
        kind = "범주" if key in categories else "수치"
        print(f"- {key} ({kind})")

    print("\n## 결측 보정 (워커가 다시 하지 않는다)")
    num_imputer = transform.named_transformers_["num"]
    for key, value in zip(numeric, num_imputer.statistics_, strict=True):
        print(f"- {key}: median {value}")
    cat_imputer = transform.named_transformers_["cat"].named_steps["fill"]
    for key, value in zip(categorical, cat_imputer.statistics_, strict=True):
        print(f"- {key}: most_frequent {value}")

    print("\n## 범주 코드 (여기 없는 값은 handle_unknown='ignore' 로 전부 0 이 된다)")
    for key, values in categories.items():
        print(f"- {key}: {values}")

    print(f"\n## 인코딩 후 폭: {len(encoded_order)}")
    print("- SHAP 기여도를 요인으로 합칠 때 쓰는 순서다")
    print(f"- {encoded_order}")

    print("\n## SHAP explainer (run_baseline.explain 과 같아야 한다)")
    print("    explainer = shap.TreeExplainer(")
    print("        model.named_steps['forest'],")
    print("        data=background,                      # 고정된 .npy, float32")
    print("        feature_perturbation='interventional',")
    print("        model_output='probability',")
    print("    )")
    print("    values = np.asarray(explainer.shap_values(encoded, check_additivity=False))")
    print("    positive = values[:, :, 1]                # shape (n, 인코딩 후 폭, 2)")
    print("    base = float(np.asarray(explainer.expected_value)[1])")
    print("- 가산성 확인: |base + positive.sum(axis=1) - predict_proba[:, 1]| <= 1e-2")
    print("- shap==0.50.0 고정. 버전이 바뀌면 기여도 수치가 달라져 기존 산출물과 비교가 안 된다")

    if artifact_path and disease:
        expected = json.loads(artifact_path.read_text(encoding="utf-8"))["diseases"][disease]["features"]
        actual = numeric + categorical
        print(f"\n## artifact.json 대조 ({disease})")
        if sorted(expected) == sorted(actual):
            print("- features 일치")
        else:
            print(f"- 불일치. artifact 에만: {sorted(set(expected) - set(actual))}")
            print(f"-        모델에만: {sorted(set(actual) - set(expected))}")
        if expected != actual:
            print(f"- 순서는 다르다. DataFrame 은 모델 순서를 따른다: {actual}")


def emit_background(model, disease: str, canonical: Path, train_years: list[int], out: Path) -> None:
    """run_baseline.explain 과 같은 규칙으로 background 행렬을 만들어 저장한다."""
    # 실험 의존성(pandas·shap)을 끌고 오므로 이 모드에서만 불러온다
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pandas as pd
    from run_baseline import LABELS, clean_input

    label_key, valid_codes, _ = LABELS[disease]
    frame = clean_input(pd.read_csv(canonical), train_years)
    valid = frame[frame[label_key].isin(valid_codes)]
    eligible = valid[valid[f"eligible_{disease}"]]
    train = eligible[eligible.survey_year.isin(train_years)]
    if train.empty:
        raise SystemExit(f"{train_years} 에 {disease} 학습 행이 없습니다")

    features = list(model.named_steps["transform"].transformers_[0][2]) + list(
        model.named_steps["transform"].transformers_[1][2]
    )
    reference = train[features].sample(min(REFERENCE_SIZE, len(train)), random_state=REFERENCE_SEED)
    sampled = reference.sample(min(BACKGROUND_ROWS, len(reference)), random_state=REFERENCE_SEED)
    background = model.named_steps["transform"].transform(sampled).astype(np.float32)

    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, background)
    print(f"저장: {out}  shape={background.shape}  dtype={background.dtype}")
    print("학습 행을 인코딩한 개인 단위 자료다. Git·Slack 금지. 모델 바이너리와 같은 경로로만 전달한다.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, required=True, help="model.joblib 경로")
    parser.add_argument("--artifact", type=Path, help="대조할 artifact.json (선택)")
    parser.add_argument("--disease", choices=["diabetes", "hypertension"])
    parser.add_argument("--canonical", type=Path, help="background 를 만들 canonical.csv")
    parser.add_argument("--train-years", type=int, nargs="+", default=[2022, 2023])
    parser.add_argument("--emit-background", type=Path, help="저장할 .npy 경로")
    args = parser.parse_args()

    if bool(args.canonical) != bool(args.emit_background):
        parser.error("--canonical 과 --emit-background 는 함께 씁니다")
    if args.canonical and not args.disease:
        parser.error("--canonical 을 쓰면 --disease 가 필요합니다")
    if args.artifact and not args.disease:
        parser.error("--artifact 를 쓰면 --disease 가 필요합니다")

    model = load_model(args.model)
    describe(model, args.artifact, args.disease)
    if args.canonical:
        print()
        emit_background(model, args.disease, args.canonical, args.train_years, args.emit_background)


if __name__ == "__main__":
    main()
