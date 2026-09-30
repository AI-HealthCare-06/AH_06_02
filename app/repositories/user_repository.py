from datetime import datetime, timedelta
from typing import Any

from app.core import config
from app.models.users import MotivationType, Sex, User, UserStatus

ALLOWED_UPDATE_FIELDS = [
    "nickname",
    "email",
    "birth_year",
    "sex",
    "height_cm",
    "motivation_type",
    "dm_diagnosed",
    "htn_diagnosed",
    "dm_medication",
    "htn_medication",
]
UPDATED_AT_FIELD = "updated_at"

#: 로그인 5회 연속 실패하면 10분 잠근다 (REQ-USER-004)
LOGIN_FAIL_LIMIT = 5
LOGIN_LOCK_MINUTES = 10

#: 탈퇴 후 이 기간이 지나면 식별정보와 업로드 사진을 지운다 (REQ-USER-009 · NFR-SEC-005)
PURGE_AFTER_DAYS = 30


class UserRepository:
    def __init__(self) -> None:
        self._model = User

    async def get_user(self, user_id: int) -> User | None:
        return await self._model.get_or_none(id=user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        return await self._model.get_or_none(email=email)

    async def exists_by_email(self, email: str) -> bool:
        return await self._model.filter(email=email).exists()

    async def create_user(
        self,
        email: str,
        password_hash: str,
        nickname: str,
        *,
        birth_year: int | None = None,
        sex: Sex | None = None,
        height_cm: float | None = None,
        motivation_type: MotivationType = MotivationType.COLLECT,
        dm_diagnosed: bool = False,
        htn_diagnosed: bool = False,
        dm_medication: bool = False,
        htn_medication: bool = False,
        disclaimer_agreed_at: datetime | None = None,
    ) -> User:
        return await self._model.create(
            email=email,
            password_hash=password_hash,
            nickname=nickname,
            birth_year=birth_year,
            sex=sex,
            height_cm=height_cm,
            motivation_type=motivation_type,
            dm_diagnosed=dm_diagnosed,
            htn_diagnosed=htn_diagnosed,
            dm_medication=dm_medication,
            htn_medication=htn_medication,
            disclaimer_agreed_at=disclaimer_agreed_at,
        )

    async def record_login_failure(self, user: User) -> User:
        """실패 횟수를 올리고, 한계에 닿으면 잠근다."""
        user.login_fail_count += 1
        fields = ["login_fail_count", UPDATED_AT_FIELD]

        if user.login_fail_count >= LOGIN_FAIL_LIMIT:
            user.locked_until = datetime.now(config.TIMEZONE) + timedelta(minutes=LOGIN_LOCK_MINUTES)
            fields.append("locked_until")

        await user.save(update_fields=fields)
        return user

    async def reset_login_failure(self, user: User) -> None:
        """로그인에 성공하면 실패 기록을 지운다."""
        if user.login_fail_count == 0 and user.locked_until is None:
            return
        user.login_fail_count = 0
        user.locked_until = None
        await user.save(update_fields=["login_fail_count", "locked_until", UPDATED_AT_FIELD])

    async def update_instance(self, user: User, data: dict[str, Any]) -> None:
        update_fields = []
        for key, value in data.items():
            if key in ALLOWED_UPDATE_FIELDS and value is not None:
                setattr(user, key, value)
                update_fields.append(key)
        if update_fields:
            update_fields.append(UPDATED_AT_FIELD)
            await user.save(update_fields=update_fields)

    async def grant_xp(self, user_id: int, amount: int) -> User | None:
        """경험치 지급. D가 직접 users를 쓰지 않고 이 함수를 부른다.

        레벨 공식은 4주차에 정한다. 지금은 누적만 한다.
        """
        user = await self.get_user(user_id)
        if user is None:
            return None
        user.total_xp += amount
        await user.save(update_fields=["total_xp", UPDATED_AT_FIELD])
        return user

    async def update_diagnosis(
        self,
        user: User,
        *,
        dm_diagnosed: bool,
        htn_diagnosed: bool,
        dm_medication: bool,
        htn_medication: bool,
    ) -> User:
        user.dm_diagnosed = dm_diagnosed
        user.htn_diagnosed = htn_diagnosed
        user.dm_medication = dm_medication
        user.htn_medication = htn_medication
        await user.save(
            update_fields=[
                "dm_diagnosed",
                "htn_diagnosed",
                "dm_medication",
                "htn_medication",
                UPDATED_AT_FIELD,
            ]
        )
        return user

    async def change_password(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        # 비밀번호를 바꾸면 잠금도 함께 푼다
        user.login_fail_count = 0
        user.locked_until = None
        await user.save(update_fields=["password_hash", "login_fail_count", "locked_until", UPDATED_AT_FIELD])
        return user

    async def withdraw(self, user: User) -> User:
        """행을 지우지 않고 비활성으로 돌린다. 30일 뒤 식별정보를 삭제한다."""
        user.status = UserStatus.WITHDRAWN
        user.withdrawn_at = datetime.now(config.TIMEZONE)
        await user.save(update_fields=["status", "withdrawn_at", UPDATED_AT_FIELD])
        return user
