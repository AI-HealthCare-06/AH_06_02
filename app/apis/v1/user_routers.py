from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, status

from app.dependencies.security import get_request_user
from app.dtos.envelope import ok
from app.dtos.users import (
    DiagnosisUpdateRequest,
    PasswordChangeRequest,
    UserInfoResponse,
    UserUpdateRequest,
    WithdrawRequest,
)
from app.models.users import User
from app.services.users import UserManageService

user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.get("/me", status_code=status.HTTP_200_OK)
async def user_me_info(
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, Any]:
    """USER-01 내 정보 조회."""
    return ok(UserInfoResponse.model_validate(user).model_dump(mode="json"))


@user_router.patch("/me", status_code=status.HTTP_200_OK)
async def update_user_me_info(
    update_data: UserUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserManageService, Depends(UserManageService)],
) -> dict[str, Any]:
    """USER-02 내 정보 수정."""
    updated = await service.update_user(user=user, data=update_data)
    return ok(UserInfoResponse.model_validate(updated).model_dump(mode="json"))


@user_router.patch("/me/diagnosis", status_code=status.HTTP_200_OK)
async def update_diagnosis(
    update_data: DiagnosisUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserManageService, Depends(UserManageService)],
) -> dict[str, Any]:
    """USER-03 진단·복약 이력 수정."""
    return ok(await service.update_diagnosis(user=user, data=update_data))


@user_router.patch("/me/password", status_code=status.HTTP_200_OK)
async def change_password(
    request: PasswordChangeRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserManageService, Depends(UserManageService)],
) -> dict[str, Any]:
    """USER-04 비밀번호 변경.

    명세상 변경 후 기존 리프레시 토큰을 모두 무효화해야 한다.
    무효화 목록은 Valkey에 두기로 했는데 아직 붙지 않아서, 그 부분은 남아 있다.
    """
    await service.change_password(
        user=user,
        current_password=request.current_password,
        new_password=request.new_password,
    )
    return ok({"password_changed": True})


@user_router.delete("/me", status_code=status.HTTP_200_OK)
async def withdraw(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserManageService, Depends(UserManageService)],
    request: Annotated[WithdrawRequest, Body()],
) -> dict[str, Any]:
    """USER-05 회원 탈퇴. 행을 지우지 않고 status를 withdrawn으로 바꾼다."""
    result = await service.withdraw(user=user, password=request.password)
    return ok({key: value.isoformat() for key, value in result.items()})


@user_router.get("/me/level", status_code=status.HTTP_200_OK)
async def level_info(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[UserManageService, Depends(UserManageService)],
) -> dict[str, Any]:
    """USER-06 레벨·경험치 조회."""
    return ok(await service.level_info(user))
