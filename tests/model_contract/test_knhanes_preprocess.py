import unittest

import pandas as pd

from scripts.model.preprocess_knhanes import canonicalize


class KnHANESPreprocessTest(unittest.TestCase):
    def test_special_codes_and_candidate_mapping(self):
        raw = pd.DataFrame(
            {
                "year": [2022, 2023, 2024],
                "age": [30, 40, 50],
                "sex": [1, 2, 1],
                "HE_BMI": [22, 23, 24],
                "HE_wc": [80, 81, 82],
                "sm_presnt": [0, 1, 0],
                "BD1": [1, 2, 2],
                "BD1_11": [8, 5, 9],
                "BD2_1": [8, 3, 9],
                "BE3_31": [1, 4, 99],
                "BE3_32": [88, 1, 99],
                "BE3_33": [88, 30, 99],
                "BE5_1": [1, 3, 6],
                "BE8_1": [8, 6, 2],
                "BE8_2": [0, 30, 0],
                "HE_DMfh1": [0, 0, 0],
                "HE_DMfh2": [0, 0, 0],
                "HE_DMfh3": [8, 8, 8],
                "HE_HPfh1": [0, 0, 0],
                "HE_HPfh2": [0, 0, 0],
                "HE_HPfh3": [8, 8, 8],
                "HE_DM_HbA1c": [1, 2, 3],
                "HE_HP": [1, 2, 4],
                "HE_sbp": [110, 125, 150],
                "HE_dbp": [70, 75, 95],
                "L_OUT_FQ": [7, 4, 1],
                "LS_VEG2": [1, 9, 99],
                "DE1_dg": [0, 0, 1],
                "DI1_dg": [0, 0, 1],
                "DE1_31": [8, 0, 0],
                "DE1_32": [8, 0, 0],
                "DI1_2": [8, 5, 0],
            }
        )

        result = canonicalize(raw)

        self.assertEqual(result["vegetable_frequency"].iloc[:2].tolist(), [1, 9])
        self.assertTrue(pd.isna(result["vegetable_frequency"].iloc[2]))
        self.assertEqual(result["walking_days"].iloc[:2].tolist(), [0, 3])
        self.assertEqual(result["walking_minutes"].iloc[:2].tolist(), [0, 90])
        self.assertTrue(pd.isna(result["walking_days"].iloc[2]))
        self.assertTrue(pd.isna(result["walking_minutes"].iloc[2]))
        self.assertEqual(result["alcohol_frequency"].iloc[:2].tolist(), [1, 5])
        self.assertEqual(result["alcohol_amount"].iloc[:2].tolist(), [0, 3])
        self.assertTrue(pd.isna(result["alcohol_frequency"].iloc[2]))
        self.assertTrue(pd.isna(result["alcohol_amount"].iloc[2]))

    def test_eighth_cycle_hypertension_codes_follow_ninth_cycle_definition(self):
        # 제8기(2019) HE_HP 는 1 정상 · 2 전단계(120~139/80~89) · 3 고혈압 의 3단계다.
        # 제9기는 1 정상 · 2 주의(120~129/<80) · 3 전단계(130~139/80~89) · 4 고혈압 의 4단계라
        # 2019 코드 3 이 제9기 코드 4 와 같은 정의이고, 전단계는 측정 혈압으로 주의/전단계를 가른다.
        raw = _raw_rows(
            year=[2019, 2019, 2019, 2019, 2024],
            HE_HP=[1, 2, 2, 3, 4],
            HE_sbp=[110, 125, 135, 150, 150],
            HE_dbp=[70, 75, 70, 95, 95],
        )

        result = canonicalize(raw)

        self.assertEqual(result["HE_HP"].tolist(), [1, 2, 3, 4, 4])

    def test_eighth_cycle_rejects_ninth_cycle_only_code(self):
        raw = _raw_rows(year=[2019], HE_HP=[4], HE_sbp=[150], HE_dbp=[95])

        with self.assertRaises(ValueError):
            canonicalize(raw)


def _raw_rows(**columns):
    n = len(columns["year"])
    base = {
        "age": [40] * n,
        "sex": [1] * n,
        "HE_BMI": [23] * n,
        "HE_wc": [80] * n,
        "sm_presnt": [0] * n,
        "BD1": [2] * n,
        "BD1_11": [5] * n,
        "BD2_1": [3] * n,
        "BE3_31": [4] * n,
        "BE3_32": [1] * n,
        "BE3_33": [30] * n,
        "BE5_1": [3] * n,
        "BE8_1": [6] * n,
        "BE8_2": [30] * n,
        "HE_DMfh1": [0] * n,
        "HE_DMfh2": [0] * n,
        "HE_DMfh3": [8] * n,
        "HE_HPfh1": [0] * n,
        "HE_HPfh2": [0] * n,
        "HE_HPfh3": [8] * n,
        "HE_DM_HbA1c": [1] * n,
        "L_OUT_FQ": [4] * n,
        "LS_VEG2": [1] * n,
        "DE1_dg": [0] * n,
        "DI1_dg": [0] * n,
        "DE1_31": [8] * n,
        "DE1_32": [8] * n,
        "DI1_2": [8] * n,
    }
    return pd.DataFrame(base | columns)


if __name__ == "__main__":
    unittest.main()
