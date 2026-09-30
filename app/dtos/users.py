from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.core.validators import optional_after_validator, validate_birth_year, validate_height_cm, validate_password
from app.dtos.base import BaseSerializerModel
from app.models.users import MotivationType, Sex, UserStatus


class UserUpdateRequest(BaseModel):
    nickname: Annotated[str | None, Field(None, min_length=1, max_length=50)] = None
    email: Annotated[EmailStr | None, Field(None, max_length=255)] = None
    birth_year: Annotated[int | None, Field(None), optional_after_validator(validate_birth_year)] = None
    sex: Sex | None = None
    height_cm: Annotated[float | None, Field(None), optional_after_validator(validate_height_cm)] = None
    motivation_type: MotivationType | None = None
    dm_diagnosed: bool | None = None
    htn_diagnosed: bool | None = None
    dm_medication: bool | None = None
    htn_medication: bool | None = None


class UserInfoResponse(BaseSerializerModel):
    id: int
    email: str
    nickname: str
    birth_year: int | None
    sex: Sex | None
    height_cm: Decimal | None
    motivation_type: MotivationType
    dm_diagnosed: bool
    htn_diagnosed: bool
    dm_medication: bool
    htn_medication: bool
    total_xp: int
    level: int
    status: UserStatus
    created_at: datetime


class DiagnosisUpdateRequest(BaseModel):
    """USER-03 진단·복약 이력 수정."""

    dm_diagnosed: bool
    htn_diagnosed: bool
    dm_medication: bool
    htn_medication: bool


class DiagnosisResponse(BaseSerializerModel):
    dm_diagnosed: bool
    htn_diagnosed: bool
    dm_medication: bool
    htn_medication: bool
    prediction_enabled: bool


class PasswordChangeRequest(BaseModel):
    """USER-04 비밀번호 변경."""

    current_password: str
    new_password: Annotated[str, AfterValidator(validate_password)]


class WithdrawRequest(BaseModel):
    """USER-05 회원 탈퇴. 본인 확인용 비밀번호를 받는다."""

    password: str


class WithdrawResponse(BaseSerializerModel):
    withdrawn_at: datetime
    purge_at: datetime


class LevelResponse(BaseSerializerModel):
    """USER-06 레벨·경험치 조회. 곡선은 4주차에 확정한다."""

    level: int
    total_xp: int
    current_level_xp: int
    next_level_xp: int | None
