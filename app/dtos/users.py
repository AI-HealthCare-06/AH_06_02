from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from app.core.validators import optional_after_validator, validate_birth_year, validate_height_cm
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
