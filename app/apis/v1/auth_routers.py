from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.core import config
from app.core.config import Env
from app.core.errors import AppError, ErrorCode
from app.dtos.auth import LoginRequest, SignUpRequest
from app.dtos.envelope import ok
from app.services.auth import AuthService
from app.services.jwt import JwtService

auth_router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_KEY = "refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str, expires: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_KEY,
        value=refresh_token,
        httponly=True,
        secure=config.ENV == Env.PROD,
        domain=config.COOKIE_DOMAIN or None,
        expires=expires,
    )


@auth_router.get("/check-email", status_code=status.HTTP_200_OK)
async def check_email(
    email: str,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> dict[str, Any]:
    """AUTH-01 이메일 중복 확인. 실제 차단은 AUTH-02에서 한 번 더 한다."""
    available = not await auth_service.user_repo.exists_by_email(email)
    return ok({"available": available})


@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignUpRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> dict[str, Any]:
    """AUTH-02 회원가입. 레벨 1 · 경험치 0으로 시작한다."""
    user = await auth_service.signup(request)
    tokens = await auth_service.login(user)

    _set_refresh_cookie(response, str(tokens["refresh_token"]), tokens["refresh_token"].payload["exp"])
    return ok(
        {
            "user_id": user.id,
            "access_token": str(tokens["access_token"]),
            "refresh_token": str(tokens["refresh_token"]),
        }
    )


@auth_router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> dict[str, Any]:
    """AUTH-03 로그인. 5회 연속 실패하면 10분 잠긴다 (REQ-USER-004)."""
    user = await auth_service.authenticate(request)
    tokens = await auth_service.login(user)

    _set_refresh_cookie(response, str(tokens["refresh_token"]), tokens["refresh_token"].payload["exp"])
    return ok({"user_id": user.id, "access_token": str(tokens["access_token"])})


@auth_router.get("/token/refresh", status_code=status.HTTP_200_OK)
async def token_refresh(
    jwt_service: Annotated[JwtService, Depends(JwtService)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any]:
    """AUTH-04 토큰 재발급."""
    if not refresh_token:
        raise AppError(ErrorCode.AUTH_TOKEN_INVALID, message="리프레시 토큰이 없습니다. 다시 로그인해주세요.")
    access_token = jwt_service.refresh_jwt(refresh_token)
    return ok({"access_token": str(access_token)})
