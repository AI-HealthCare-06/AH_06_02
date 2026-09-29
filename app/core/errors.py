"""공통 에러 코드와 예외.

에러 코드의 원본은 API 명세서 구글 시트 `에러 코드` 탭이다.
새 코드가 필요하면 시트에 먼저 등록하고 팀에 알린 뒤 여기에 추가한다.
코드를 임의로 만들지 않는다.
"""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    # 공통
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # A · 회원·인증
    AUTH_EMAIL_DUPLICATED = "AUTH_EMAIL_DUPLICATED"
    AUTH_WEAK_PASSWORD = "AUTH_WEAK_PASSWORD"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_ACCOUNT_LOCKED = "AUTH_ACCOUNT_LOCKED"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"

    # C · 건강정보
    HLTH_PROFILE_INCOMPLETE = "HLTH_PROFILE_INCOMPLETE"
    HLTH_VALUE_OUT_OF_RANGE = "HLTH_VALUE_OUT_OF_RANGE"
    HLTH_RECORD_NOT_FOUND = "HLTH_RECORD_NOT_FOUND"

    # B · 예측
    PRED_ALL_DIAGNOSED = "PRED_ALL_DIAGNOSED"
    PRED_INPUT_INSUFFICIENT = "PRED_INPUT_INSUFFICIENT"
    PRED_NOT_FOUND = "PRED_NOT_FOUND"

    # D · 챌린지·보상·도감
    CHLG_LIMIT_EXCEEDED = "CHLG_LIMIT_EXCEEDED"
    CHLG_ALREADY_ACTIVE = "CHLG_ALREADY_ACTIVE"
    CHLG_SAFETY_CONFIRMATION_REQUIRED = "CHLG_SAFETY_CONFIRMATION_REQUIRED"
    CHLG_NOT_ACTIVE = "CHLG_NOT_ACTIVE"
    CHLG_NOT_FOUND = "CHLG_NOT_FOUND"
    CHLG_LOG_DUPLICATED = "CHLG_LOG_DUPLICATED"
    CHLG_VERIFICATION_FAILED = "CHLG_VERIFICATION_FAILED"
    CHLG_RECOMMENDATION_NOT_FOUND = "CHLG_RECOMMENDATION_NOT_FOUND"
    CHLG_RECOMMENDATION_UNAVAILABLE = "CHLG_RECOMMENDATION_UNAVAILABLE"
    CHLG_INVALID_COOLDOWN = "CHLG_INVALID_COOLDOWN"


#: 코드 -> (HTTP 상태, 사용자에게 보이는 기본 메시지)
#: 메시지는 화면에 그대로 뜬다. 겁주는 표현과 진단 표현을 쓰지 않는다.
ERROR_SPEC: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.VALIDATION_ERROR: (400, "입력값을 다시 확인해주세요."),
    ErrorCode.UNAUTHORIZED: (401, "로그인이 필요합니다."),
    ErrorCode.FORBIDDEN: (403, "접근 권한이 없습니다."),
    ErrorCode.NOT_FOUND: (404, "요청하신 정보를 찾을 수 없습니다."),
    ErrorCode.INTERNAL_ERROR: (500, "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."),
    ErrorCode.AUTH_EMAIL_DUPLICATED: (409, "이미 가입된 이메일입니다."),
    ErrorCode.AUTH_WEAK_PASSWORD: (
        422,
        "비밀번호는 8자 이상이며 영문과 숫자를 각각 1자 이상 포함해야 합니다.",
    ),
    ErrorCode.AUTH_INVALID_CREDENTIALS: (401, "이메일 또는 비밀번호가 올바르지 않습니다."),
    ErrorCode.AUTH_ACCOUNT_LOCKED: (403, "로그인 5회 실패로 10분간 잠겼습니다. 잠시 후 다시 시도해주세요."),
    ErrorCode.AUTH_TOKEN_EXPIRED: (401, "로그인이 만료되었습니다. 다시 로그인해주세요."),
    ErrorCode.AUTH_TOKEN_INVALID: (401, "로그인 정보가 올바르지 않습니다. 다시 로그인해주세요."),
    ErrorCode.HLTH_PROFILE_INCOMPLETE: (400, "출생연도, 성별, 키를 먼저 입력해주세요."),
    ErrorCode.HLTH_VALUE_OUT_OF_RANGE: (400, "입력하신 값이 허용 범위를 벗어났습니다."),
    ErrorCode.HLTH_RECORD_NOT_FOUND: (404, "해당 건강정보 기록을 찾을 수 없습니다."),
    ErrorCode.PRED_ALL_DIAGNOSED: (400, "두 질환 모두 진단 이력이 있어 예측을 제공하지 않습니다."),
    ErrorCode.PRED_INPUT_INSUFFICIENT: (400, "예측에 필요한 항목이 부족합니다."),
    ErrorCode.PRED_NOT_FOUND: (404, "완료된 예측 결과가 없습니다."),
    ErrorCode.CHLG_LIMIT_EXCEEDED: (409, "동시에 진행할 수 있는 챌린지는 3개까지입니다."),
    ErrorCode.CHLG_ALREADY_ACTIVE: (409, "이미 진행 중인 챌린지입니다."),
    ErrorCode.CHLG_SAFETY_CONFIRMATION_REQUIRED: (400, "운동형 챌린지는 안전 확인이 필요합니다."),
    ErrorCode.CHLG_NOT_ACTIVE: (409, "진행 중인 챌린지가 아닙니다."),
    ErrorCode.CHLG_NOT_FOUND: (404, "해당 챌린지를 찾을 수 없습니다."),
    ErrorCode.CHLG_LOG_DUPLICATED: (409, "같은 날 같은 슬롯에 이미 기록이 있습니다."),
    ErrorCode.CHLG_VERIFICATION_FAILED: (422, "인증 방식에 맞지 않는 값입니다."),
    ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND: (404, "해당 추천 카드를 찾을 수 없습니다."),
    ErrorCode.CHLG_RECOMMENDATION_UNAVAILABLE: (409, "추천을 만들 근거가 아직 없습니다."),
    ErrorCode.CHLG_INVALID_COOLDOWN: (400, "쿨다운 값이 올바르지 않습니다."),
}


class AppError(Exception):
    """서비스에서 의도적으로 내는 에러.

    사용 예::

        raise AppError(ErrorCode.AUTH_EMAIL_DUPLICATED)
        raise AppError(ErrorCode.AUTH_WEAK_PASSWORD, extra={"unmet": ["min_length"]})
        raise AppError(ErrorCode.VALIDATION_ERROR, message="이메일 형식이 올바르지 않습니다.")
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        default_status, default_message = ERROR_SPEC[code]
        self.code = code
        self.message = message or default_message
        self.status_code = status_code or default_status
        self.extra = extra or {}
        super().__init__(f"{code}: {self.message}")
