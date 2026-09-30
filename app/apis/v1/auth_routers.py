from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.core import config
from app.core.config import Env
from app.core.errors import AppError, ErrorCode
from app.dependencies.security import get_request_user
from app.dtos.auth import LoginRequest, SignUpRequest, TokenRefreshRequest
from app.dtos.envelope import ok
from app.models.users import User
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
    return ok(
        {
            "access_token": str(tokens["access_token"]),
            "refresh_token": str(tokens["refresh_token"]),
            "user": {
                "id": user.id,
                "nickname": user.nickname,
                "level": user.level,
                "total_xp": user.total_xp,
            },
        }
    )


@auth_router.post("/refresh", status_code=status.HTTP_200_OK)
async def token_refresh(
    jwt_service: Annotated[JwtService, Depends(JwtService)],
    request: TokenRefreshRequest | None = None,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any]:
    """AUTH-04 토큰 재발급.

    명세대로 본문의 refresh_token을 먼저 본다.
    본문이 비어 있으면 로그인 때 심어둔 httpOnly 쿠키로 대신한다.
    """
    token = request.refresh_token if request else refresh_token
    if not token:
        raise AppError(ErrorCode.AUTH_TOKEN_INVALID, message="리프레시 토큰이 없습니다. 다시 로그인해주세요.")
    return ok({"access_token": str(jwt_service.refresh_jwt(token))})


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    _: Annotated[User, Depends(get_request_user)],
) -> dict[str, Any]:
    """AUTH-05 로그아웃.

    인증 쿠키를 만료시킨다. 이미 로그아웃된 상태에서 다시 불러도 200으로 답한다.

    명세상 서버에서 리프레시 토큰을 무효화해야 하는데, 무효화 목록을 Valkey에 두기로
    해서 Valkey가 붙은 뒤에 이어 붙인다. 지금은 쿠키만 지운다.
    """
    response.delete_cookie(key=REFRESH_COOKIE_KEY, domain=config.COOKIE_DOMAIN or None)
    return ok({"logged_out": True})
