from tortoise.contrib.test import TestCase

from app.core.leveling import MAX_LEVEL, XP_THRESHOLDS
from app.models.users import User
from app.repositories.user_repository import UserRepository

# 곡선은 4주차에 바뀌는 임시값이라 숫자를 직접 쓰지 않고 XP_THRESHOLDS 에서 경계를 읽는다


async def _user(email: str, total_xp: int = 0) -> User:
    return await User.create(
        email=email, password_hash="x", nickname="t", total_xp=total_xp, level=1 if total_xp == 0 else MAX_LEVEL
    )


class TestGrantXp(TestCase):
    async def test_one_short_of_the_boundary_does_not_level_up(self) -> None:
        user = await _user("xp-short@example.com")

        result = await UserRepository().grant_xp(user.id, XP_THRESHOLDS[2] - 1)

        assert result is not None
        assert (result.level_up, result.new_level) == (False, 1)
        assert (await User.get(id=user.id)).level == 1

    async def test_exactly_on_the_boundary_levels_up(self) -> None:
        user = await _user("xp-exact@example.com")
        repo = UserRepository()
        await repo.grant_xp(user.id, XP_THRESHOLDS[2] - 1)

        result = await repo.grant_xp(user.id, 1)

        assert result is not None
        assert (result.level_up, result.new_level, result.total_xp) == (True, 2, XP_THRESHOLDS[2])
        saved = await User.get(id=user.id)
        assert (saved.level, saved.total_xp) == (2, XP_THRESHOLDS[2])

    async def test_two_levels_in_one_grant(self) -> None:
        user = await _user("xp-double@example.com")

        result = await UserRepository().grant_xp(user.id, XP_THRESHOLDS[3])

        assert result is not None
        assert (result.level_up, result.new_level) == (True, 3)
        assert (await User.get(id=user.id)).level == 3

    async def test_xp_keeps_accumulating_at_max_level(self) -> None:
        user = await _user("xp-max@example.com", total_xp=XP_THRESHOLDS[MAX_LEVEL])

        result = await UserRepository().grant_xp(user.id, 500)

        assert result is not None
        assert (result.level_up, result.new_level) == (False, MAX_LEVEL)
        assert result.total_xp == XP_THRESHOLDS[MAX_LEVEL] + 500
        saved = await User.get(id=user.id)
        assert (saved.level, saved.total_xp) == (MAX_LEVEL, XP_THRESHOLDS[MAX_LEVEL] + 500)

    async def test_unknown_user_returns_none(self) -> None:
        assert await UserRepository().grant_xp(987654, 10) is None
