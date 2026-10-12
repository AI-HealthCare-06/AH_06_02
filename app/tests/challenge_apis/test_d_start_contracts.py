"""예정 이용일과 시작 전 대상 변경의 HTTP 계약을 확인한다."""

import asyncio
from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise import connections
from tortoise.contrib.test import TestCase, TruncationTestCase

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.main import app
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    ChallengeRecommendation,
    MonsterState,
    UserAttackCycle,
    UserChallenge,
    UserChallengeOccurrence,
    UserMonster,
)
from app.models.users import User
from app.services.attack_cycles import AttackCycleService, today_kst
from app.services.challenges import ChallengeCoreService
from app.tests.auth_apis.test_signup_api import signup_body
from app.tests.d_fixtures import make_card, make_cycle, make_target
from scripts.seed.seed_challenges import DEFAULT_CSV, parse_rows, read_csv, upsert_challenges


class TestDStartContracts(TestCase):
    async def prepare(self, client: AsyncClient) -> tuple[User, dict[str, str], UserAttackCycle]:
        await client.post("/api/v1/auth/signup", json=signup_body(email="d-contract@example.com"))
        response = await client.post(
            "/api/v1/auth/login", json={"email": "d-contract@example.com", "password": "dango1234"}
        )
        user = await User.get(email="d-contract@example.com")
        headers = {"Authorization": f"Bearer {response.json()['data']['access_token']}"}
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        cycle = await make_cycle(user.id, ["physical_activity_low", "smoking_current"])
        return user, headers, cycle

    async def test_event_starts_only_on_confirmed_usage_dates(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, cycle = await self.prepare(client)
            challenge = await Challenge.get(code="CH_WALK_ONE_STOP")
            card = await make_card(user.id, challenge, cycle)
            today = today_kst(datetime.now(config.TIMEZONE))
            dates = [today + timedelta(days=1), today + timedelta(days=3)]

            response = await client.post(
                "/api/v1/user-challenges",
                headers=headers,
                json={"recommendation_ids": [card.id], "scheduled_dates": [str(day) for day in dates]},
            )

        assert response.status_code == 201, response.text
        item = response.json()["data"]["items"][0]
        rows = await UserChallengeOccurrence.filter(user_challenge_id=item["user_challenge_id"]).order_by(
            "scheduled_date"
        )
        assert [row.scheduled_date for row in rows] == dates
        assert item["goal_config_snapshot"]["scheduled_dates"] == [str(day) for day in dates]

    async def test_invalid_usage_dates_do_not_activate_cycle_or_create_missions(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, cycle = await self.prepare(client)
            challenge = await Challenge.get(code="CH_WALK_ONE_STOP")
            card = await make_card(user.id, challenge, cycle)
            today = today_kst()
            for days in (
                [],
                [str(today)] * 2,
                [str(today - timedelta(days=1))],
                [str(today + timedelta(days=28))],
                ["2026-02-30"],
                [0],
                [str(today) + "T00:00:00"],
            ):
                response = await client.post(
                    "/api/v1/user-challenges",
                    headers=headers,
                    json={"recommendation_ids": [card.id], "scheduled_dates": days},
                )
                assert response.status_code == 400, response.text
                assert response.json()["error"]["code"] == "VALIDATION_ERROR"
                await cycle.refresh_from_db()
                assert cycle.status == AttackCycleStatus.DRAFT
                assert await UserChallenge.filter(user_id=user.id).count() == 0

    async def test_mixed_start_without_dates_rolls_back_every_selected_card(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, cycle = await self.prepare(client)
            daily = await make_card(user.id, await Challenge.get(code="CH_WALK_AFTER_MEAL"), cycle)
            event = await make_card(user.id, await Challenge.get(code="CH_WALK_ONE_STOP"), cycle)
            response = await client.post(
                "/api/v1/user-challenges",
                headers=headers,
                json={"recommendation_ids": [daily.id, event.id], "safety_confirmed": True},
            )
        assert response.status_code == 400
        await cycle.refresh_from_db()
        assert cycle.status == AttackCycleStatus.DRAFT
        assert await UserChallenge.filter(user_id=user.id).count() == 0
        assert await ChallengeRecommendation.filter(id__in=[daily.id, event.id], action__isnull=True).count() == 2

    async def test_week_two_usage_dates_respect_original_cycle_end(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, cycle = await self.prepare(client)
            today = today_kst()
            end = today + timedelta(days=20)
            await UserAttackCycle.filter(id=cycle.id).update(
                status=AttackCycleStatus.ACTIVE,
                start_date=today - timedelta(days=7),
                end_date=end,
            )
            card = await make_card(user.id, await Challenge.get(code="CH_WALK_ONE_STOP"), cycle)
            invalid = await client.post(
                "/api/v1/user-challenges",
                headers=headers,
                json={"recommendation_ids": [card.id], "scheduled_dates": [str(end + timedelta(days=1))]},
            )
            assert invalid.status_code == 400
            valid = await client.post(
                "/api/v1/user-challenges",
                headers=headers,
                json={"recommendation_ids": [card.id], "scheduled_dates": [str(end), str(today)]},
            )
        assert valid.status_code == 201, valid.text
        item = valid.json()["data"]["items"][0]
        assert item["end_date"] == str(end)
        mission = await UserChallenge.get(id=item["user_challenge_id"])
        assert mission.duration_days_snapshot == 21
        await cycle.refresh_from_db()
        assert cycle.extra_added_count == 1

    async def test_draft_target_change_invalidates_old_cards_and_preserves_progress(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, cycle = await self.prepare(client)
            challenge = await Challenge.get(code="CH_NO_SMOKE_TODAY")
            old_card = await make_card(user.id, challenge, cycle)
            target = await make_target(user.id, ["physical_activity_low"])
            target.weekly_progress = 135
            target.seal_count = 2
            await target.save()
            response = await client.patch(
                "/api/v1/attack-cycles/current/target", headers=headers, json={"user_monster_id": target.id}
            )

        assert response.status_code == 200, response.text
        assert response.json()["data"]["target_user_monster_id"] == target.id
        await cycle.refresh_from_db()
        await target.refresh_from_db()
        assert cycle.status == AttackCycleStatus.DRAFT and cycle.start_date is None
        assert cycle.target_user_monster_id == target.id
        assert target.weekly_progress == 135 and target.seal_count == 2
        assert not await ChallengeRecommendation.filter(id=old_card.id).exists()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            stale = await client.post(
                "/api/v1/user-challenges",
                headers=headers,
                json={"recommendation_ids": [old_card.id]},
            )
        assert stale.status_code == 404
        assert await UserChallenge.filter(user_id=user.id).count() == 0

    async def test_target_change_rejects_started_cycles_and_foreign_or_unmeasured_targets(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            user, headers, cycle = await self.prepare(client)
            await client.post("/api/v1/auth/signup", json=signup_body(email="other-contract@example.com"))
            other = await User.get(email="other-contract@example.com")
            foreign = await make_target(other.id, ["smoking_current"])
            response = await client.patch(
                "/api/v1/attack-cycles/current/target", headers=headers, json={"user_monster_id": foreign.id}
            )
            assert response.status_code == 404 and response.json()["error"]["code"] == "CHLG_NOT_FOUND"
            target = await make_target(user.id, ["smoking_current"])
            await UserMonster.filter(id=target.id).update(state=MonsterState.UNMEASURED, impact_score=None)
            response = await client.patch(
                "/api/v1/attack-cycles/current/target", headers=headers, json={"user_monster_id": target.id}
            )
            assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"
            await UserMonster.filter(id=target.id).update(state=MonsterState.RAGE, impact_score=80)
            card = await make_card(user.id, await Challenge.get(code="CH_NO_SMOKE_TODAY"), cycle)
            response = await client.post(
                "/api/v1/user-challenges", headers=headers, json={"recommendation_ids": [card.id]}
            )
            assert response.status_code == 201
            before = cycle.target_user_monster_id
            response = await client.patch(
                "/api/v1/attack-cycles/current/target", headers=headers, json={"user_monster_id": target.id}
            )
            assert response.status_code == 409 and response.json()["error"]["code"] == "CHLG_NOT_ACTIVE"
            await cycle.refresh_from_db()
            assert cycle.target_user_monster_id == before


class TestConcurrentTargetChange(TruncationTestCase):
    async def test_concurrent_start_and_target_change_keep_one_consistent_target(self) -> None:
        if connections.get("models").capabilities.dialect != "mysql":
            self.skipTest("MySQL 사용자 행 잠금이 필요한 시작·대상 변경 경합 검증")
        await upsert_challenges(parse_rows(read_csv(DEFAULT_CSV)))
        challenge = await Challenge.get(code="CH_WALK_AFTER_MEAL")
        for round_no in range(3):
            user = await User.create(email=f"target-race-{round_no}@example.com", password_hash="x", nickname="검증")
            cycle = await make_cycle(user.id, ["physical_activity_low"])
            old_target_id = cycle.target_user_monster_id
            new_target = await make_target(user.id, ["smoking_current"])
            card = await make_card(user.id, challenge, cycle)
            outcomes = await asyncio.gather(
                ChallengeCoreService().start_from_recommendations(
                    user_id=user.id,
                    recommendation_ids=[card.id],
                    safety_confirmed=True,
                ),
                AttackCycleService().change_draft_target(user.id, new_target.id),
                return_exceptions=True,
            )
            errors = [item for item in outcomes if isinstance(item, BaseException)]
            assert len(errors) == 1, outcomes
            assert isinstance(errors[0], AppError)
            assert errors[0].code in {ErrorCode.CHLG_NOT_ACTIVE, ErrorCode.CHLG_RECOMMENDATION_NOT_FOUND}
            await cycle.refresh_from_db()
            missions = await UserChallenge.filter(user_id=user.id)
            if missions:
                assert len(missions) == 1 and cycle.status == AttackCycleStatus.ACTIVE
                assert cycle.target_user_monster_id == old_target_id
            else:
                assert cycle.status == AttackCycleStatus.DRAFT
                assert cycle.target_user_monster_id == new_target.id
