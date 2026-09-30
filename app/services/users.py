from tortoise.transactions import in_transaction

from app.dtos.users import UserUpdateRequest
from app.models.users import User
from app.repositories.user_repository import UserRepository
from app.services.auth import AuthService


class UserManageService:
    def __init__(self) -> None:
        self.repo = UserRepository()
        self.auth_service = AuthService()

    async def update_user(self, user: User, data: UserUpdateRequest) -> User:
        if data.email and str(data.email) != user.email:
            await self.auth_service.check_email_exists(str(data.email))

        async with in_transaction():
            await self.repo.update_instance(user=user, data=data.model_dump(exclude_none=True))
            await user.refresh_from_db()
        return user
