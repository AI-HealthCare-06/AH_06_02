from datetime import datetime, timedelta

from tortoise.transactions import in_transaction

from app.core.errors import AppError, ErrorCode
from app.core.leveling import level_progress
from app.core.utils.security import hash_password, verify_password
from app.dtos.users import DiagnosisUpdateRequest, UserUpdateRequest
from app.models.users import User
from app.repositories.user_repository import PURGE_AFTER_DAYS, UserRepository
from app.services.auth import AuthService


def prediction_enabled(user: User) -> bool:
    """예측 화면을 보여줄지 여부.

    기획서 v19 2.3 기준이다. 진단은 질환 단위로 보고,
    두 질환을 모두 진단받은 경우에만 예측 전체를 감춘다.
    한 질환만 진단받았다면 나머지 한 질환의 예측은 그대로 제공한다.
    """
    return not (user.dm_diagnosed and user.htn_diagnosed)


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

    async def update_diagnosis(self, user: User, data: DiagnosisUpdateRequest) -> dict[str, bool]:
        """USER-03. 진단 여부가 바뀌면 예측 노출과 챌린지 추천 경로가 함께 바뀐다."""
        updated = await self.repo.update_diagnosis(
            user,
            dm_diagnosed=data.dm_diagnosed,
            htn_diagnosed=data.htn_diagnosed,
            dm_medication=data.dm_medication,
            htn_medication=data.htn_medication,
        )
        return {
            "dm_diagnosed": updated.dm_diagnosed,
            "htn_diagnosed": updated.htn_diagnosed,
            "dm_medication": updated.dm_medication,
            "htn_medication": updated.htn_medication,
            "prediction_enabled": prediction_enabled(updated),
        }

    async def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """USER-04. 현재 비밀번호를 확인한 뒤 바꾼다."""
        if not verify_password(current_password, user.password_hash):
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, message="현재 비밀번호가 올바르지 않습니다.")

        if verify_password(new_password, user.password_hash):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="현재 비밀번호와 다른 값으로 설정해주세요.",
                extra={"field": "new_password"},
            )

        await self.repo.change_password(user, hash_password(new_password))

    async def withdraw(self, user: User, password: str) -> dict[str, datetime]:
        """USER-05. 행을 지우지 않고 비활성으로 돌린다."""
        if not verify_password(password, user.password_hash):
            raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, message="비밀번호가 올바르지 않습니다.")

        withdrawn = await self.repo.withdraw(user)
        withdrawn_at = withdrawn.withdrawn_at
        assert withdrawn_at is not None  # withdraw()가 방금 채웠다
        return {
            "withdrawn_at": withdrawn_at,
            "purge_at": withdrawn_at + timedelta(days=PURGE_AFTER_DAYS),
        }

    async def level_info(self, user: User) -> dict[str, int | None]:
        """USER-06. 레벨 곡선은 4주차에 확정한다."""
        level, current_level_xp, next_level_xp = level_progress(user.total_xp)
        return {
            "level": level,
            "total_xp": user.total_xp,
            "current_level_xp": current_level_xp,
            "next_level_xp": next_level_xp,
        }
