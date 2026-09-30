from datetime import datetime

from tortoise.transactions import in_transaction

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.core.utils.security import hash_password, verify_password
from app.dtos.auth import LoginRequest, SignUpRequest
from app.models.users import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.services.jwt import JwtService


class AuthService:
    def __init__(self) -> None:
        self.user_repo = UserRepository()
        self.jwt_service = JwtService()

    async def signup(self, data: SignUpRequest) -> User:
        if not data.disclaimer_agreed:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="참고용 고지에 동의해야 가입할 수 있습니다.",
                extra={"field": "disclaimer_agreed"},
            )

        await self.check_email_exists(str(data.email))

        async with in_transaction():
            return await self.user_repo.create_user(
                email=str(data.email),
                password_hash=hash_password(data.password),
                nickname=data.nickname,
                birth_year=data.birth_year,
                sex=data.sex,
                height_cm=data.height_cm,
                motivation_type=data.motivation_type,
                dm_diagnosed=data.dm_diagnosed,
                htn_diagnosed=data.htn_diagnosed,
                dm_medication=data.dm_medication,
                htn_medication=data.htn_medication,
                disclaimer_agreed_at=datetime.now(config.TIMEZONE),
            )

    async def authenticate(self, data: LoginRequest) -> User:
        user = await self.user_repo.get_user_by_email(str(data.email))

        # 없는 이메일과 틀린 비밀번호를 같은 응답으로 돌려준다.
        # 다르게 주면 어떤 이메일이 가입돼 있는지 알려주는 셈이다.
        if user is None:
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS)

        if user.status is UserStatus.WITHDRAWN:
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS)

        if user.locked_until is not None and user.locked_until > datetime.now(config.TIMEZONE):
            raise AppError(ErrorCode.AUTH_ACCOUNT_LOCKED)

        if not verify_password(data.password, user.password_hash):
            await self.user_repo.record_login_failure(user)
            if user.locked_until is not None and user.locked_until > datetime.now(config.TIMEZONE):
                raise AppError(ErrorCode.AUTH_ACCOUNT_LOCKED)
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS)

        await self.user_repo.reset_login_failure(user)
        return user

    async def login(self, user: User) -> dict[str, AccessToken | RefreshToken]:
        return self.jwt_service.issue_jwt_pair(user)

    async def check_email_exists(self, email: str) -> None:
        if await self.user_repo.exists_by_email(email):
            raise AppError(ErrorCode.AUTH_EMAIL_DUPLICATED)
