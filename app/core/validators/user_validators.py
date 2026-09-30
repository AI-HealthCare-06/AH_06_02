import re
from datetime import datetime

from app.core import config

#: 만 14세 미만은 가입할 수 없다 (서비스 약관)
MIN_AGE = 14
#: 출생연도 하한. 이보다 앞선 값은 오타로 본다
MIN_BIRTH_YEAR = 1900


def password_unmet_rules(password: str) -> list[str]:
    """비밀번호 규칙 중 지키지 못한 항목을 돌려준다.

    기준은 REQ-USER-002다. 8자 이상, 영문과 숫자를 각각 1자 이상.
    화면에서 무엇이 모자란지 짚어주려고 목록으로 돌려준다.
    """
    unmet = []
    if len(password) < 8:
        unmet.append("min_length")
    if not re.search(r"[A-Za-z]", password):
        unmet.append("needs_letter")
    if not re.search(r"[0-9]", password):
        unmet.append("needs_digit")
    return unmet


def validate_password(password: str) -> str:
    if password_unmet_rules(password):
        raise ValueError("비밀번호는 8자 이상이며 영문과 숫자를 각각 1자 이상 포함해야 합니다.")
    return password


def validate_birth_year(birth_year: int) -> int:
    this_year = datetime.now(tz=config.TIMEZONE).year

    if birth_year < MIN_BIRTH_YEAR or birth_year > this_year:
        raise ValueError(f"출생연도는 {MIN_BIRTH_YEAR}년부터 {this_year}년 사이여야 합니다.")

    if this_year - birth_year < MIN_AGE:
        raise ValueError(f"서비스 약관에 따라 만 {MIN_AGE}세 미만은 회원가입이 불가합니다.")

    return birth_year


def validate_height_cm(height_cm: float) -> float:
    if not 50 <= height_cm <= 250:
        raise ValueError("키는 50cm 이상 250cm 이하로 입력해주세요.")
    return height_cm
