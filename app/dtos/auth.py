from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.core.validators import validate_birth_year, validate_height_cm, validate_password
from app.dtos.base import BaseSerializerModel
from app.models.users import MotivationType, Sex


class SignUpRequest(BaseModel):
    """AUTH-02 회원가입 요청. API 명세서 A 탭 기준이다."""

    email: Annotated[EmailStr, Field(max_length=255)]
    password: Annotated[str, AfterValidator(validate_password)]
    nickname: Annotated[str, Field(min_length=1, max_length=50)]

    birth_year: Annotated[int | None, Field(None), AfterValidator(validate_birth_year)] = None
    sex: Sex | None = None
    height_cm: Annotated[float | None, Field(None), AfterValidator(validate_height_cm)] = None
    motivation_type: MotivationType = MotivationType.COLLECT

    dm_diagnosed: bool
    htn_diagnosed: bool
    dm_medication: bool
    htn_medication: bool

    disclaimer_agreed: Annotated[bool, Field(description="참고용 고지 동의. true여야 가입 가능 (REQ-USER-010)")]


class SignUpResponse(BaseSerializerModel):
    user_id: int
    access_token: str
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenRefreshRequest(BaseModel):
    """AUTH-04 토큰 재발급. 로그인 때 받은 리프레시 토큰을 본문으로 보낸다."""

    refresh_token: str
