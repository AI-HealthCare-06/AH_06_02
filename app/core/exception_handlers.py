"""전역 예외 핸들러.

모든 에러 응답이 같은 봉투로 나가게 한다.
``main.py``에서 ``register_exception_handlers(app)`` 한 줄만 부르면 된다.
"""

import logging
from typing import Any

import orjson
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import ERROR_SPEC, AppError, ErrorCode

logger = logging.getLogger(__name__)

#: FastAPI·Starlette가 직접 올리는 HTTP 상태를 우리 코드로 옮긴다
STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
}


def _error_response(
    status_code: int,
    code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> Response:
    body: dict[str, Any] = {"code": code, "message": message}
    if extra:
        body.update(extra)
    return Response(
        status_code=status_code,
        content=orjson.dumps({"success": False, "error": body}),
        media_type="application/json",
    )


async def app_error_handler(request: Request, exc: AppError) -> Response:
    return _error_response(exc.status_code, str(exc.code), exc.message, exc.extra)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> Response:
    """Pydantic 검증 실패. 어떤 필드가 왜 틀렸는지 함께 내려준다."""
    status_code, message = ERROR_SPEC[ErrorCode.VALIDATION_ERROR]
    fields = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
            "reason": err.get("msg", ""),
        }
        for err in exc.errors()
    ]
    return _error_response(
        status_code,
        str(ErrorCode.VALIDATION_ERROR),
        message,
        {"fields": fields},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    """라이브러리나 기존 코드가 올린 HTTPException을 봉투에 맞춘다.

    사용자에게는 우리 한국어 기본 메시지를 보내고, 원래 detail은 로그에만 남긴다.
    Starlette와 템플릿 코드가 영어 문구를 그대로 내보내기 때문이다.
    새 코드에서는 ``HTTPException`` 대신 ``AppError``를 쓴다.
    """
    code = STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    _, message = ERROR_SPEC[code]
    if exc.detail:
        logger.info(
            "HTTPException %s %s %s · detail=%s",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
        )
    return _error_response(exc.status_code, str(code), message)


async def unhandled_error_handler(request: Request, exc: Exception) -> Response:
    """예상 못 한 예외. 내부 사정을 사용자에게 보여주지 않는다."""
    logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
    status_code, message = ERROR_SPEC[ErrorCode.INTERNAL_ERROR]
    return _error_response(status_code, str(ErrorCode.INTERNAL_ERROR), message)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
