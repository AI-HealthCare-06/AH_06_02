"""공통 응답 봉투.

API 명세서 `공통 규칙` 탭 기준이다.

    성공  { "success": true,  "data": { ... } }
    실패  { "success": false, "error": { "code": "...", "message": "..." } }

템플릿 기본형인 ``{"detail": ...}``는 쓰지 않는다.
"""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ErrorBody(BaseModel):
    """에러 본문. ``unmet`` 같은 부가 필드를 더 담을 수 있다."""

    model_config = ConfigDict(extra="allow")

    code: str
    message: str


class ErrorResponse(BaseModel):
    success: Literal[False] = False
    error: ErrorBody


class SuccessResponse(BaseModel, Generic[T]):
    success: Literal[True] = True
    data: T


def ok(data: Any) -> dict[str, Any]:
    """성공 응답 본문을 만든다.

    라우터에서::

        return ok({"available": True})
    """
    return {"success": True, "data": data}


def fail(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """실패 응답 본문을 만든다. 보통은 ``AppError``를 올리고 핸들러에 맡긴다."""
    return {"success": False, "error": {"code": code, "message": message, **extra}}
