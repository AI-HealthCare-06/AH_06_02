"""app 과 ai_worker 의 factor 계약이 어긋나지 않는지 확인한다.

app 이미지에는 ai_worker 가 들어가지 않아 상수를 옮겨 적었다 (app/services/model_artifact.py).
테스트는 이미지 밖에서 돌므로 두 쪽을 직접 비교할 수 있다.
"""

from ai_worker import model_contract
from app.services.model_artifact import FACTOR_DICTIONARY_VERSION, IMMUTABLE_FACTORS, is_modifiable


def test_immutable_factors_match_ai_worker() -> None:
    assert IMMUTABLE_FACTORS == model_contract.IMMUTABLE_FACTORS


def test_factor_dictionary_version_matches_ai_worker() -> None:
    assert FACTOR_DICTIONARY_VERSION == model_contract.FACTOR_DICTIONARY_VERSION


def test_is_modifiable_matches_rank_contributions() -> None:
    grouped = dict.fromkeys((*model_contract.IMMUTABLE_FACTORS, "bmi_high", "smoking_current"), 0.1)
    rows = model_contract.rank_contributions(grouped)
    assert rows
    for row in rows:
        assert is_modifiable(row["factor_key"]) == row["modifiable"]
