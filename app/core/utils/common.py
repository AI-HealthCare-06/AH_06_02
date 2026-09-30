from datetime import datetime

from app.core import config


def age_from_birth_year(birth_year: int | None) -> int | None:
    """출생연도로 나이를 계산한다.

    나이를 저장하지 않고 조회할 때 계산하는 이유는, 저장해두면 해가 바뀔 때 틀어지기 때문이다.
    """
    if birth_year is None:
        return None
    return datetime.now(tz=config.TIMEZONE).year - birth_year
