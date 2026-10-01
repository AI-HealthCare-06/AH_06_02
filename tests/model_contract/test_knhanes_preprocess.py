import unittest

import pandas as pd

from scripts.model.preprocess_knhanes import canonicalize


class KnHANESPreprocessTest(unittest.TestCase):
    def test_vegetable_frequency_keeps_ls_veg2_categories_and_missing(self):
        raw = pd.DataFrame(
            {
                "year": [2022, 2023, 2024],
                "age": [30, 40, 50],
                "sex": [1, 2, 1],
                "HE_BMI": [22, 23, 24],
                "HE_wc": [80, 81, 82],
                "sm_presnt": [0, 1, 0],
                "BD1": [1, 2, 2],
                "BD1_11": [8, 5, 4],
                "BD2_1": [8, 3, 2],
                "BE3_31": [1, 4, 8],
                "BE3_32": [0, 1, 1],
                "BE3_33": [0, 30, 0],
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


if __name__ == "__main__":
    unittest.main()
