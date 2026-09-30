from typing import Literal, overload

from app.core.errors import AppError, ErrorCode
from app.core.jwt.exceptions import ExpiredTokenError, TokenError
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.models.users import User


class JwtService:
    access_token_class = AccessToken
    refresh_token_class = RefreshToken

    def create_access_token(self, user: User) -> AccessToken:
        return self.access_token_class.for_user(user)

    def create_refresh_token(self, user: User) -> RefreshToken:
        return self.refresh_token_class.for_user(user)

    @overload
    def verify_jwt(
        self,
        token: str,
        token_type: Literal["access"],
    ) -> AccessToken: ...

    @overload
    def verify_jwt(
        self,
        token: str,
        token_type: Literal["refresh"],
    ) -> RefreshToken: ...

    def verify_jwt(self, token: str, token_type: Literal["access", "refresh"]) -> AccessToken | RefreshToken:
        token_class: type[AccessToken | RefreshToken]
        if token_type == "access":
            token_class = self.access_token_class
        else:
            token_class = self.refresh_token_class

        try:
            return token_class(token=token)
        except ExpiredTokenError as err:
            raise AppError(ErrorCode.AUTH_TOKEN_EXPIRED) from err
        except TokenError as err:
            raise AppError(ErrorCode.AUTH_TOKEN_INVALID) from err

    def refresh_jwt(self, refresh_token: str) -> AccessToken:
        verified_rt = self.verify_jwt(token=refresh_token, token_type="refresh")
        return verified_rt.access_token

    def issue_jwt_pair(self, user: User) -> dict[str, AccessToken | RefreshToken]:
        rt = self.create_refresh_token(user)
        at = rt.access_token
        return {"access_token": at, "refresh_token": rt}
