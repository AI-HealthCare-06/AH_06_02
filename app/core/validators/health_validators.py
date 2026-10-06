from decimal import Decimal
from typing import Any

#: 건강정보 허용 범위. 벗어나면 저장하지 않고 400과 허용 범위를 함께 돌려준다 (REQ-HLTH-003).
#: 근거가 있는 필드만 둔다. 허리둘레·이완기 혈압·HbA1c·지질은 명세에 범위가 없어 DB 타입 한계만 본다.
HEALTH_VALUE_RANGES: dict[str, tuple[int, int]] = {
    # REQ-HLTH-003
    "weight_kg": (30, 200),
    "sbp": (70, 250),
    "fasting_glucose": (40, 500),
    # table-spec 주석
    "walking_days": (0, 7),
    "strength_days": (0, 7),
    "dining_out_freq": (1, 7),
    # docs/03_ai_data/input-code-map.md canonical 값
    "alcohol_frequency": (1, 6),
    "alcohol_amount": (0, 5),
    "walking_minutes": (0, 1440),
    "sitting_minutes": (0, 1440),
}

#: alcohol_amount 0은 최근 비음주(alcohol_frequency=1)에 동반될 때만 유효하다 (input-code-map.md)
NON_DRINKER_FREQUENCY = 1


def health_value_violations(values: dict[str, Any]) -> list[dict[str, Any]]:
    """허용 범위를 벗어난 필드를 허용 범위와 함께 돌려준다. 값이 없는 필드는 보지 않는다."""
    violations: list[dict[str, Any]] = []
    for field, (low, high) in HEALTH_VALUE_RANGES.items():
        value = values.get(field)
        if value is not None and not low <= Decimal(str(value)) <= high:
            violations.append({"field": field, "min": low, "max": high})

    if values.get("alcohol_amount") == 0 and values.get("alcohol_frequency") != NON_DRINKER_FREQUENCY:
        violations.append(
            {
                "field": "alcohol_amount",
                "min": 1,
                "max": HEALTH_VALUE_RANGES["alcohol_amount"][1],
                "reason": "음주량 0은 음주 빈도가 '최근 안 마심'일 때만 입력할 수 있습니다.",
            }
        )
    return violations
