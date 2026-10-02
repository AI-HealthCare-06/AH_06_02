import unittest

from ai_worker.model_contract import assess_threat_eligibility


class ThreatEligibilityTest(unittest.TestCase):
    def test_requires_storable_p95_and_twenty_expected_upper_tail_rows(self):
        eligible, reason = assess_threat_eligibility(0.00001, 400)
        self.assertTrue(eligible)
        self.assertEqual(reason, "p95_resolvable_with_at_least_20_expected_upper_tail_rows")

    def test_rejects_p95_below_contribution_storage_precision(self):
        eligible, reason = assess_threat_eligibility(0.000009, 1000)
        self.assertFalse(eligible)
        self.assertEqual(reason, "positive_shap_p95_below_storage_precision")

    def test_rejects_p95_with_insufficient_positive_support(self):
        eligible, reason = assess_threat_eligibility(0.01, 399)
        self.assertFalse(eligible)
        self.assertEqual(reason, "fewer_than_20_expected_rows_above_positive_p95")


if __name__ == "__main__":
    unittest.main()
