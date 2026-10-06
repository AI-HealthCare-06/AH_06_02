import pytest

from app.core.validators.user_validators import MAX_HEIGHT_CM, MIN_HEIGHT_CM, validate_height_cm


class TestHeightRange:
    """REQ-HLTH-003 의 키 100~250cm 를 지킨다."""

    def test_range_matches_the_requirement(self) -> None:
        assert (MIN_HEIGHT_CM, MAX_HEIGHT_CM) == (100, 250)

    @pytest.mark.parametrize("height_cm", [49.0, 99.9, 250.1, 300.0])
    def test_rejects_out_of_range(self, height_cm: float) -> None:
        with pytest.raises(ValueError):
            validate_height_cm(height_cm)

    @pytest.mark.parametrize("height_cm", [100.0, 164.0, 250.0])
    def test_accepts_in_range(self, height_cm: float) -> None:
        assert validate_height_cm(height_cm) == height_cm
