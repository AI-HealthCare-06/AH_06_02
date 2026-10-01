"""Offline baseline on verified canonical input, never on undocumented raw codes.

Run with --data data/canonical.csv --out data/experiment --seeds 42 43 44.
The 2024 test set is untouched unless --final-variant is explicitly selected.
"""

import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ai_worker.model_contract import (  # noqa: E402
    FACTOR_DICTIONARY_VERSION,
    FEATURE_FACTOR,
    IMMUTABLE_FACTORS,
    assess_threat_eligibility,
    global_importance,
    group_shap,
)

BASE = [
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
CORE_WITH_SITTING = BASE + ["sitting_minutes"]
CANDIDATES = {
    "sodium": "dining_out_freq",
    "sitting": "sitting_minutes",
    "vegetable": "vegetable_frequency",
}
VARIANT_CHOICES = [
    "base",
    "sodium",
    "sitting",
    "vegetable",
    "sodium_sitting",
    "sodium_vegetable",
    "sitting_vegetable",
    "all_candidates",
]
CATEGORICAL = [
    "sex",
    "smoking_current",
    "alcohol_frequency",
    "alcohol_amount",
    "family_history_dm",
    "family_history_htn",
    "dining_out_freq",
    "vegetable_frequency",
]
# KNHANES IX guide and all three raw annual label domains verified.
LABELS = {"diabetes": ("HE_DM_HbA1c", [1, 2, 3], 3), "hypertension": ("HE_HP", [1, 2, 3, 4], 4)}


def clean_input(frame):
    required = set(BASE + ["survey_year", "HE_DM_HbA1c", "HE_HP"])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing canonical columns: {sorted(missing)}")
    if not set(frame.survey_year.unique()) <= {2022, 2023, 2024}:
        raise ValueError("Unexpected survey_year")
    if frame.age.isna().any() or (frame.age < 19).any():
        raise ValueError("Canonical input must contain verified adults only")
    bounds = {
        "walking_days": (0, 7),
        "strength_days": (0, 7),
        "walking_minutes": (0, 1440),
        "sitting_minutes": (0, 1440),
    }
    for key, (low, high) in bounds.items():
        if key in frame and not frame[key].dropna().between(low, high).all():
            raise ValueError(f"Invalid canonical units/range: {key}")
    if not set(frame.sex.dropna()) <= {"M", "F"}:
        raise ValueError("sex requires verified M/F canonical mapping")
    for key in ["smoking_current", "family_history_dm", "family_history_htn"]:
        if not set(frame[key].dropna()) <= {0, 1}:
            raise ValueError(f"Unmapped binary code: {key}")
    validate_candidate_categories(frame)
    # Category codes must already have been checked against official annual codebooks.
    return frame.copy()


def pipeline(features, seed):
    numeric = [key for key in features if key not in CATEGORICAL]
    categorical = [key for key in features if key in CATEGORICAL]
    transform = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median", keep_empty_features=True), numeric),
            (
                "cat",
                Pipeline(
                    [
                        ("fill", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                        ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical,
            ),
        ]
    )
    forest = RandomForestClassifier(n_estimators=200, min_samples_leaf=10, max_depth=10, random_state=seed, n_jobs=-1)
    return Pipeline([("transform", transform), ("forest", forest)])


def validate_candidate_categories(frame):
    for key, allowed in {
        "dining_out_freq": range(1, 8),
        "vegetable_frequency": range(1, 10),
    }.items():
        if key in frame and not frame[key].dropna().isin(allowed).all():
            raise ValueError(f"Unmapped {key} code")


def metrics(labels, probability, threshold=None):
    if len(np.unique(labels)) != 2:
        raise ValueError("Both target classes are needed for evaluation")
    false_positive, true_positive, thresholds = roc_curve(labels, probability)
    if threshold is None:
        candidates = np.flatnonzero((true_positive >= 0.70) & np.isfinite(thresholds))
        chosen = min(candidates, key=lambda index: (false_positive[index], -thresholds[index]))
        threshold = float(thresholds[chosen])
    predicted = probability >= threshold
    return {
        "n": len(labels),
        "positive_n": int(labels.sum()),
        "auroc": float(roc_auc_score(labels, probability)),
        "average_precision": float(average_precision_score(labels, probability)),
        "brier": float(brier_score_loss(labels, probability)),
        "threshold": threshold,
        "recall": float(predicted[labels == 1].mean()),
        "specificity": float((~predicted[labels == 0]).mean()),
    }


def explain(model, reference, evaluation, features, seed):
    transform = model.named_steps["transform"]
    numeric = [key for key in features if key not in CATEGORICAL]
    categorical = [key for key in features if key in CATEGORICAL]
    feature_order = numeric.copy()
    for key, categories in zip(
        categorical, transform.named_transformers_["cat"].named_steps["encode"].categories_, strict=True
    ):
        feature_order.extend([key] * len(categories))
    background = transform.transform(reference.sample(min(100, len(reference)), random_state=seed)).astype(np.float32)
    encoded = transform.transform(evaluation).astype(np.float32)
    explainer = shap.TreeExplainer(
        model.named_steps["forest"], data=background, feature_perturbation="interventional", model_output="probability"
    )
    values = np.asarray(explainer.shap_values(encoded, check_additivity=False))
    if values.ndim != 3 or values.shape[2] != 2:
        raise ValueError(f"Unexpected SHAP shape: {values.shape}")
    positive = values[:, :, 1]
    base = float(np.asarray(explainer.expected_value)[1])
    predicted = model.predict_proba(evaluation)[:, 1]
    additivity_error = float(np.max(np.abs(base + positive.sum(axis=1) - predicted)))
    # SHAP 0.50 / sklearn 1.8 leaves small float32-vs-probability rounding errors.
    if additivity_error > 1e-2:
        raise ValueError(f"Probability-space SHAP additivity failed: max error {additivity_error:.6g}")
    encoded_mapping = {str(index): FEATURE_FACTOR[key] for index, key in enumerate(feature_order)}
    grouped = [group_shap(dict(enumerate_row(row)), encoded_mapping) for row in positive]
    return grouped, base, additivity_error


def enumerate_row(row):
    return [(str(index), float(value)) for index, value in enumerate(row)]


def run_one(frame, features, disease, seed, final_test, artifact_dir, reference_size=256):
    label_key, valid_codes, positive_code = LABELS[disease]
    valid = frame[frame[label_key].isin(valid_codes)].copy()
    eligible = valid[valid[f"eligible_{disease}"]].copy()
    train = eligible[eligible.survey_year == 2022]
    validation = eligible[eligible.survey_year == 2023]
    if any(part.empty or part[label_key].eq(positive_code).nunique() != 2 for part in [train, validation]):
        raise ValueError(f"Missing years/classes: {disease}")
    if train[features].isna().all().any():
        raise ValueError("An all-missing feature cannot be silently retained")
    model = pipeline(features, seed)
    model.fit(train[features], train[label_key].eq(positive_code).astype(int))
    result = metrics(
        validation[label_key].eq(positive_code).to_numpy(), model.predict_proba(validation[features])[:, 1]
    )
    # Use a bounded sample for a quick pass, or the complete 2022 training set for final scale references.
    train_reference = (
        train[features]
        if reference_size == 0
        else train[features].sample(min(reference_size, len(train)), random_state=42)
    )
    validation_reference = validation[features].sample(min(256, len(validation)), random_state=42)
    train_grouped, base, train_additivity_error = explain(model, train[features], train_reference, features, seed)
    validation_grouped, _, validation_additivity_error = explain(
        model, train[features], validation_reference, features, seed
    )
    supported_factors = {FEATURE_FACTOR[key] for key in features}
    reference_p95 = {}
    for factor in sorted(supported_factors):
        signed = np.asarray([float(row[factor]) for row in train_grouped])
        positive_shap = signed[signed > 0]
        p95 = float(np.quantile(positive_shap, 0.95)) if len(positive_shap) else 0.0
        threat_eligible, eligibility_reason = assess_threat_eligibility(p95, len(positive_shap))
        reference_p95[factor] = {
            "positive_shap_p95": p95,
            "positive_n": int((positive_shap > 0).sum()),
            "reference_n": len(train_grouped),
            "reference_year": 2022,
            "threat_eligible": threat_eligible,
            "threat_eligibility_reason": eligibility_reason,
        }
    global_scores = {item["factor_key"]: float(item["normalized_score"]) for item in global_importance(train_grouped)}
    paired_scores = {}
    for factor in sorted(supported_factors - IMMUTABLE_FACTORS):
        p95 = reference_p95[factor]["positive_shap_p95"]
        global_score = global_scores[factor]
        if p95 <= 0 or global_score <= 0:
            paired_scores[factor] = {"n": 0, "reason": "zero_positive_p95_or_global_score"}
            continue
        personal = np.asarray([min(max(float(row[factor]), 0.0) / p95 * 100.0, 100.0) for row in validation_grouped])
        break_even = personal / global_score
        paired_scores[factor] = {
            "n": len(personal),
            "global_normalized_score": global_score,
            "personal_threat_score_quantiles": {
                str(q): float(np.quantile(personal, q)) for q in [0.0, 0.25, 0.5, 0.75, 0.95, 1.0]
            },
            "break_even_behavior_weight_quantiles": {
                str(q): float(np.quantile(break_even, q)) for q in [0.0, 0.25, 0.5, 0.75, 0.95, 1.0]
            },
            "global_path_wins_at_candidate_weight": {
                str(weight): float((global_score * weight >= personal).mean()) for weight in [0.25, 0.5, 0.75, 1.0]
            },
        }
    report = {
        "validation": result,
        "train_n": len(train),
        "train_positive_n": int(train[label_key].eq(positive_code).sum()),
        "label_valid_before_diagnosis_medication_filter_n": int(len(valid[valid.survey_year == 2022])),
        "excluded_diagnosed_or_medicated_n": int(len(valid[valid.survey_year == 2022]) - len(train)),
        "excluded_label_n": int((~frame[label_key].isin(valid_codes)).sum()),
        "feature_missing_fraction": {key: float(train[key].isna().mean()) for key in features},
        "train_shap_reference_n": len(train_reference),
        "validation_shap_reference_n": len(validation_reference),
        "base_value": base,
        "shap_additivity_max_abs_error": {
            "train_reference": train_additivity_error,
            "validation_reference": validation_additivity_error,
            "tolerance": 0.01,
        },
        "global_importance_train_sample": global_importance(train_grouped),
        "validation_importance": global_importance(validation_grouped),
        "positive_shap_p95_training_reference": reference_p95,
        "same_user_contribution_vs_global_weight_candidates": paired_scores,
    }
    for feature in ["sitting_minutes", "dining_out_freq", "vegetable_frequency"]:
        if feature in features:
            factor = FEATURE_FACTOR[feature]
            audit = pd.DataFrame(
                {"value": validation_reference[feature].to_numpy(), "shap": [row[factor] for row in validation_grouped]}
            )
            audit["band"] = pd.qcut(audit.value, q=4, duplicates="drop")
            report[f"{feature}_bands"] = [
                {"band": str(band), "n": len(part), "mean_signed_shap": float(part.shap.mean())}
                for band, part in audit.groupby("band", observed=True)
            ]
    if final_test:
        test = eligible[eligible.survey_year == 2024]
        report["test"] = metrics(
            test[label_key].eq(positive_code).to_numpy(), model.predict_proba(test[features])[:, 1], result["threshold"]
        )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_dir / "model.joblib")
    artifact = {
        "status": "experiment_only_not_deployable",
        "model_version": f"knhanes-ix-{disease}-{variant_name(features)}-s{seed}",
        "disease": disease,
        "features": features,
        "seed": seed,
        "split": {"train": 2022, "validation": 2023, "test": 2024},
        "test_evaluated": bool(final_test),
        "validation_metrics": result,
        "test_metrics": report.get("test"),
        "global_importance": report["global_importance_train_sample"],
        "positive_shap_p95_training_reference": reference_p95,
        "shap_additivity_max_abs_error": report["shap_additivity_max_abs_error"],
    }
    (artifact_dir / "artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    # Person-level SHAP rows stay under git-ignored data/ for the local audit.
    pd.DataFrame(train_grouped).to_csv(artifact_dir / "train_shap.csv", index=False)
    pd.DataFrame(validation_grouped).to_csv(artifact_dir / "validation_shap.csv", index=False)
    validation_reference.to_csv(artifact_dir / "validation_features.csv", index=False)
    return report


def variant_name(features):
    candidates = [name for name, feature in CANDIDATES.items() if feature in features]
    return "_".join(["base", *candidates])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44])
    parser.add_argument("--variants", nargs="+", choices=VARIANT_CHOICES)
    parser.add_argument("--final-variant", choices=VARIANT_CHOICES)
    parser.add_argument("--diseases", nargs="+", choices=LABELS, default=list(LABELS))
    parser.add_argument(
        "--reference-size",
        type=int,
        default=256,
        help="2022 train rows for SHAP scale calculation; 0 uses all eligible 2022 train rows",
    )
    args = parser.parse_args()
    if args.reference_size < 0:
        parser.error("--reference-size must be 0 (all rows) or a positive integer")
    frame = clean_input(pd.read_csv(args.data))
    variant_candidates = {
        "base": (),
        "sodium": ("sodium",),
        "sitting": ("sitting",),
        "vegetable": ("vegetable",),
        "sodium_sitting": ("sodium", "sitting"),
        "sodium_vegetable": ("sodium", "vegetable"),
        "sitting_vegetable": ("sitting", "vegetable"),
        "all_candidates": tuple(CANDIDATES),
    }
    variants = {
        name: BASE + [CANDIDATES[candidate] for candidate in candidates]
        for name, candidates in variant_candidates.items()
        if all(CANDIDATES[candidate] in frame.columns for candidate in candidates)
    }
    if args.final_variant:
        if args.final_variant not in variants:
            parser.error(f"Variant {args.final_variant!r} needs candidate columns missing from the canonical CSV")
        variants = {args.final_variant: variants[args.final_variant]}
    elif args.variants:
        absent = set(args.variants) - set(variants)
        if absent:
            parser.error(f"Variants need candidate columns missing from the canonical CSV: {sorted(absent)}")
        variants = {name: variants[name] for name in args.variants}
    report = {
        "status": "experiment_only_not_deployable",
        "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
        "factor_dictionary_version": FACTOR_DICTIONARY_VERSION,
        "packages": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn", "shap"]},
        "split": {"train": 2022, "validation": 2023, "test": 2024},
        "test_evaluated": bool(args.final_variant),
        "diseases": args.diseases,
        "reference_size_requested": args.reference_size,
        "runs": [],
    }
    for variant, features in variants.items():
        for disease in args.diseases:
            for seed in args.seeds:
                result = run_one(
                    frame,
                    features,
                    disease,
                    seed,
                    bool(args.final_variant),
                    args.out / f"{variant}-{disease}-{seed}",
                    args.reference_size,
                )
                report["runs"].append(
                    {"variant": variant, "disease": disease, "seed": seed, "features": features, **result}
                )
                print(variant, disease, seed, result["validation"], flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
