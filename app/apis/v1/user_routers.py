from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_request_user
from app.dtos.envelope import ok
from app.dtos.users import UserInfoResponse, UserUpdateRequest
from app.models.users import User
from app.services.users import UserManageService

user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.get("/me", status_code=status.HTTP_200_OK)
async def user_me_info(
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, Any]:
    return ok(UserInfoResponse.model_validate(user).model_dump(mode="json"))


@user_router.patch("/me", status_code=status.HTTP_200_OK)
async def update_user_me_info(
    update_data: UserUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    user_manage_service: Annotated[UserManageService, Depends(UserManageService)],
) -> dict[str, Any]:
    updated = await user_manage_service.update_user(user=user, data=update_data)
    return ok(UserInfoResponse.model_validate(updated).model_dump(mode="json"))
