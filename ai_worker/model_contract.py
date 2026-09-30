"""B explanation contracts. No model weights or health records are embedded here."""

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

FEATURE_FACTOR = {
    "age": "age",
    "sex": "sex",
    "bmi": "bmi_high",
    "waist_cm": "waist_high",
    "smoking_current": "smoking_current",
    "alcohol_frequency": "alcohol_frequency",
    "alcohol_amount": "alcohol_amount",
    "walking_days": "physical_activity_low",
    "walking_minutes": "physical_activity_low",
    "strength_days": "strength_activity_low",
    "family_history_dm": "family_history_dm",
    "family_history_htn": "family_history_htn",
    "dining_out_freq": "sodium_behavior",
    "sitting_minutes": "sedentary_time_high",
    "vegetable_frequency": "vegetable_intake_low",
}
IMMUTABLE_FACTORS = frozenset({"age", "sex", "family_history_dm", "family_history_htn"})
DISEASES = frozenset({"diabetes", "hypertension"})
FACTOR_DICTIONARY_VERSION = "v0.1-sedentary"
MONSTER_FACTORS = {
    "alde": ("alcohol_frequency", "alcohol_amount"),
    "cotinine": ("smoking_current",),
    "viscera": ("bmi_high", "waist_high", "physical_activity_low", "strength_activity_low", "sedentary_time_high"),
    "sodi": ("sodium_behavior",),
}


def finite(value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite model output")
    return number


def group_shap(raw: Mapping[str, float], feature_factor: Mapping[str, str] = FEATURE_FACTOR) -> dict[str, float]:
    """Each raw/encoded feature must map to exactly one factor; preserve signs."""
    groups: dict[str, float] = {}
    for feature, value in raw.items():
        factor = feature_factor[feature]  # Unknown features fail closed.
        groups[factor] = groups.get(factor, 0.0) + finite(value)
    return groups


def rank_contributions(grouped: Mapping[str, float]) -> list[dict[str, Any]]:
    """Use stored precision for deterministic ranks and omit zero rows."""
    values = {key: round(finite(value), 5) for key, value in grouped.items()}
    keys = sorted((key for key, value in values.items() if value != 0), key=lambda key: (-abs(values[key]), key))
    return [
        {
            "factor_key": key,
            "contribution": values[key],
            "direction": "increase" if values[key] > 0 else "decrease",
            "rank": index,
            "modifiable": key not in IMMUTABLE_FACTORS,
        }
        for index, key in enumerate(keys, 1)
    ]


def global_importance(grouped_rows: Sequence[Mapping[str, float]]) -> list[dict[str, Any]]:
    if not grouped_rows:
        raise ValueError("Training SHAP reference is empty")
    keys = set(grouped_rows[0])
    if any(set(row) != keys for row in grouped_rows):
        raise ValueError("Inconsistent factor sets")
    scores = {key: sum(abs(finite(row[key])) for row in grouped_rows) / len(grouped_rows) for key in keys}
    maximum = max(scores.values(), default=0.0)
    return [
        {
            "factor_key": key,
            "importance": scores[key],
            "normalized_score": 100.0 * scores[key] / maximum if maximum else 0.0,
            "modifiable": key not in IMMUTABLE_FACTORS,
            "rank": rank,
        }
        for rank, key in enumerate(sorted(keys, key=lambda key: (-scores[key], key)), 1)
    ]


def monster_scores(
    grouped: Mapping[str, float], disease: str, supported_factors: set[str] | None = None
) -> dict[str, float]:
    if disease not in DISEASES:
        raise ValueError("Unsupported disease")
    supported = set(FEATURE_FACTOR.values()) if supported_factors is None else supported_factors
    required = {factor for factors in MONSTER_FACTORS.values() for factor in factors if factor in supported}
    if required - set(grouped):
        raise ValueError("Missing supported factor contributions")
    return {
        monster: sum(max(finite(grouped[factor]), 0.0) for factor in factors if factor in supported)
        for monster, factors in MONSTER_FACTORS.items()
        if (monster != "sodi" or disease == "hypertension") and any(factor in supported for factor in factors)
    }


def hp_from_fixed_scale(score: float, scale: float | None) -> int | None:
    """Legacy aggregate-score helper; not the agreed factor-level threat calibration."""
    value = finite(score)
    if scale is None:
        return None
    scale_value = finite(scale)
    if scale_value <= 0:
        return None
    return math.floor(100.0 * min(max(value / scale_value, 0.0), 1.0) + 0.5)


def threat_from_reference_p95(
    signed_shap: float, p95_reference: float | None, threat_eligible: bool = True
) -> int | None:
    """Convert one factor's positive SHAP to 0..100 using its fixed reference P95."""
    value = finite(signed_shap)
    if not threat_eligible or p95_reference is None:
        return None
    scale = finite(p95_reference)
    if scale <= 0:
        return None
    positive_shap = max(value, 0.0)
    return math.floor(100.0 * min(positive_shap / scale, 1.0) + 0.5)


class ModelExplanationService:
    """Internal B -> D provider; callers must enforce authenticated ownership.

    Loaders should return durable artifacts/committed predictions, never dummy data.
    Returns the arrays specified by the team's internal module-call contract.
    Public HTTP metadata/envelopes belong to the route layer, not these helpers.
    This helper does not implement persistence, public routes or the worker loop.
    """

    def __init__(
        self,
        artifact_loader: Callable[[], Mapping[str, Any]],
        prediction_loader: Callable[[int], Mapping[str, Any]],
    ) -> None:
        self.artifact_loader = artifact_loader
        self.prediction_loader = prediction_loader

    @staticmethod
    def _validate(disease: str, limit: int) -> None:
        if disease not in DISEASES or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("disease or limit is invalid")

    def get_global_importance(self, disease: str, limit: int) -> list[dict[str, Any]]:
        self._validate(disease, limit)
        artifact = self.artifact_loader()
        if artifact.get("status") != "trained" or not artifact.get("model_version"):
            raise ValueError("MODEL_UNAVAILABLE")
        return [
            {
                "factor_key": item["factor_key"],
                "importance": item["importance"],
                "normalized_score": item["normalized_score"],
                "rank": item["rank"],
                "model_version": artifact["model_version"],
            }
            for item in artifact["diseases"][disease]["global_importance"][:limit]
        ]

    def get_top_contributions(self, prediction_id: int, disease: str, limit: int) -> list[dict[str, Any]]:
        self._validate(disease, limit)
        prediction = self.prediction_loader(prediction_id)
        if prediction.get("status") != "done":
            raise ValueError("PREDICTION_NOT_READY")
        return [
            {
                "factor_key": item["factor_key"],
                "contribution": item["contribution"],
                "direction": item["direction"],
                "rank": item["rank"],
            }
            for item in sorted(prediction["contributions"][disease], key=lambda item: item["rank"])[:limit]
        ]
