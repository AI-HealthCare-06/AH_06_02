"""임시 테스트 도구: 테스트 계정만 주기 종료를 앞당길 수 있다. 도구를 지울 때 이 파일도 지운다."""

from datetime import timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core import config
from app.dependencies.security import get_request_user
from app.main import app
from app.models.challenges import AttackCycleStatus, Challenge, UserAttackCycle, UserChallenge, UserChallengeStatus
from app.models.users import User
from app.services.attack_cycles import AttackCycleService, today_kst
from app.tests.d_fixtures import make_cycle


async def _active_cycle_with_two_missions(user: User) -> UserAttackCycle:
    start = today_kst() - timedelta(days=3)
    cycle = await make_cycle(user.id, ["smoking_current"], start=start)
    for code in ("CH_NO_SMOKE_TODAY", "CH_DELAY_FIRST_CIG"):
        challenge = await Challenge.create(
            code=code,
            title=code,
            category="smoking",
            factor_key="smoking_current",
            goal_type="boolean",
            verification_type="manual",
        )
        await UserChallenge.create(
            user_id=user.id,
            challenge_id=challenge.id,
            cycle_id=cycle.id,
            status=UserChallengeStatus.ACTIVE,
            start_date=start,
            end_date=cycle.end_date,
            duration_days_snapshot=28,
            daily_target_count_snapshot=1,
        )
    return cycle


async def _call(user: User, method: str, path: str) -> tuple[int, dict]:
    app.dependency_overrides[get_request_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.request(method, f"/api/v1/test-tools{path}")
        return response.status_code, response.json()
    finally:
        app.dependency_overrides.clear()


class TestTestTools(TestCase):
    async def test_other_accounts_get_not_found_and_cycle_stays(self):
        user = await User.create(email="someone@example.com", password_hash="x", nickname="일반")
        cycle = await _active_cycle_with_two_missions(user)
        with patch.object(config, "TEST_TOOL_EMAILS", "tester@example.com"):
            status, body = await _call(user, "POST", "/attack-cycle/finish")
        assert status == 404
        assert body["error"]["code"] == "NOT_FOUND"
        await cycle.refresh_from_db()
        assert cycle.status == AttackCycleStatus.ACTIVE

    async def test_empty_setting_closes_tool_for_everyone(self):
        user = await User.create(email="tester@example.com", password_hash="x", nickname="테스트")
        with patch.object(config, "TEST_TOOL_EMAILS", ""):
            status, _ = await _call(user, "GET", "/attack-cycle")
        assert status == 404

    async def test_finish_closes_cycle_like_day_28_and_frees_slots(self):
        user = await User.create(email="Tester@Example.com", password_hash="x", nickname="테스트")
        cycle = await _active_cycle_with_two_missions(user)
        with patch.object(config, "TEST_TOOL_EMAILS", "other@example.com, tester@example.com"):
            status, before = await _call(user, "GET", "/attack-cycle")
            assert status == 200
            assert before["data"]["remaining_slots"] == 0
            status, body = await _call(user, "POST", "/attack-cycle/finish")
        assert status == 200
        data = body["data"]
        assert data["finished"] is True
        assert data["closed_cycle_id"] == cycle.id
        assert data["ended_challenges"] == 2
        await cycle.refresh_from_db()
        assert cycle.status == AttackCycleStatus.COMPLETED
        assert cycle.end_date == today_kst() - timedelta(days=1)
        # 실제 28일 종료와 같이 미션은 '기간 종료'(graduated)가 된다
        assert set(await UserChallenge.filter(user_id=user.id).values_list("status", flat=True)) == {
            UserChallengeStatus.GRADUATED
        }
        # 진행 중 주기가 없으니 다음 추천이 새 주기를 연다
        assert await AttackCycleService().get_active(user.id) is None

    async def test_finish_without_active_cycle_changes_nothing(self):
        user = await User.create(email="tester@example.com", password_hash="x", nickname="테스트")
        with patch.object(config, "TEST_TOOL_EMAILS", "tester@example.com"):
            status, body = await _call(user, "POST", "/attack-cycle/finish")
        assert status == 200
        assert body["data"]["finished"] is False
        assert body["data"]["cycle"] is None
        assert await UserAttackCycle.filter(user_id=user.id).count() == 0
