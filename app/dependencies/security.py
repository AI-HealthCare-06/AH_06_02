from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AppError, ErrorCode
from app.models.users import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.services.jwt import JwtService

security = HTTPBearer()


async def get_request_user(credential: Annotated[HTTPAuthorizationCredentials, Depends(security)]) -> User:
    """토큰을 검증하고 사용자를 돌려준다.

    토큰이 만료·위조인 경우는 JwtService가 AppError로 올린다.
    """
    verified = JwtService().verify_jwt(token=credential.credentials, token_type="access")

    user = await UserRepository().get_user(verified.payload["user_id"])
    if user is None or user.status is UserStatus.WITHDRAWN:
        raise AppError(ErrorCode.AUTH_TOKEN_INVALID)
    return user
