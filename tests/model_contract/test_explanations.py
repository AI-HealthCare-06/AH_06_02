import unittest

from ai_worker.model_contract import (
    ModelExplanationService,
    global_importance,
    group_shap,
    hp_from_fixed_scale,
    monster_scores,
    rank_contributions,
)


class ExplanationContractTest(unittest.TestCase):
    def test_signed_grouping_and_sedentary_are_independent(self):
        result = group_shap({"walking_days": 0.07, "walking_minutes": -0.05, "sitting_minutes": 0.03})
        self.assertAlmostEqual(result["physical_activity_low"], 0.02)
        self.assertAlmostEqual(result["sedentary_time_high"], 0.03)
        self.assertAlmostEqual(sum(result.values()), 0.05)

    def test_group_cancellation_precedes_global_absolute_value(self):
        rows = [group_shap({"walking_days": 0.3, "walking_minutes": -0.3})]
        self.assertEqual(global_importance(rows)[0]["importance"], 0)

    def test_rank_uses_magnitude_tie_break_and_omits_rounded_zero(self):
        rows = rank_contributions({"sex": -0.1, "age": 0.1, "bmi_high": 0.0000001})
        self.assertEqual([row["factor_key"] for row in rows], ["age", "sex"])
        self.assertEqual(rows[1]["direction"], "decrease")
        self.assertFalse(rows[0]["modifiable"])

    def test_hp_missing_scale_is_not_zero(self):
        self.assertIsNone(hp_from_fixed_scale(0.2, None))
        self.assertIsNone(hp_from_fixed_scale(0.2, 0))
        self.assertEqual(hp_from_fixed_scale(-0.1, 0.2), 0)
        self.assertEqual(hp_from_fixed_scale(0.1, 0.2), 50)
        self.assertEqual(hp_from_fixed_scale(0.8, 0.2), 100)

    def test_hp_excludes_immutable_and_measured_spike(self):
        scores = monster_scores(
            {"age": 0.5, "sodium_behavior": 0.1, "bmi_high": -0.2},
            "diabetes",
            {"age", "sodium_behavior", "bmi_high"},
        )
        self.assertNotIn("spike", scores)
        self.assertNotIn("sodi", scores)
        self.assertEqual(scores["viscera"], 0)

    def test_missing_supported_factor_is_not_healthy_zero(self):
        with self.assertRaises(ValueError):
            monster_scores({"bmi_high": -0.2}, "diabetes")

    def test_nonfinite_unknown_features_and_invalid_limits_fail(self):
        with self.assertRaises(ValueError):
            group_shap({"age": float("nan")})
        with self.assertRaises(KeyError):
            group_shap({"fasting_glucose": 0.1})
        service = ModelExplanationService(lambda: {}, lambda _: {})
        with self.assertRaises(ValueError):
            service.get_global_importance("diabetes", 0)
        with self.assertRaises(ValueError):
            service.get_global_importance("diabetes", 3)

    def test_global_contract_exposes_current_version_without_changing_artifact(self):
        importance = global_importance([{"age": 0.3, "bmi_high": 0.1}])
        artifact = {
            "status": "trained",
            "model_version": "old",
            "factor_dictionary_version": "v0",
            "diseases": {"diabetes": {"global_importance": importance}},
        }
        service = ModelExplanationService(lambda: artifact, lambda _: {})
        old_rows = service.get_global_importance("diabetes", 1)
        self.assertEqual(old_rows, [{"factor_key": "age", "importance": 0.3, "rank": 1, "model_version": "old"}])
        artifact["model_version"] = "new"
        new_rows = service.get_global_importance("diabetes", 3)
        self.assertEqual(len(new_rows), 2)
        self.assertTrue(all(row["model_version"] == "new" for row in new_rows))
        self.assertEqual(old_rows[0]["model_version"], "old")
        self.assertIn("normalized_importance", importance[0])
        self.assertIn("modifiable", importance[0])
        self.assertNotIn("model_version", importance[0])

    def test_prediction_uses_saved_contributions_after_retraining(self):
        def active_artifact_must_not_be_used():
            self.fail("A saved prediction must not be reinterpreted using the current model")

        loaded_prediction_ids = []

        def load_prediction(prediction_id):
            loaded_prediction_ids.append(prediction_id)
            return {
                "status": "done",
                "model_version": "old",
                "factor_dictionary_version": "v0",
                "contributions": {"diabetes": list(reversed(rank_contributions({"age": 0.3, "bmi_high": -0.1})))},
            }

        service = ModelExplanationService(
            active_artifact_must_not_be_used,
            load_prediction,
        )
        self.assertEqual(
            service.get_top_contributions(501, "diabetes", 1),
            [{"factor_key": "age", "contribution": 0.3, "direction": "increase", "rank": 1}],
        )
        self.assertEqual(loaded_prediction_ids, [501])


if __name__ == "__main__":
    unittest.main()
