from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.utils.security import hash_password, verify_password
from app.models.challenges import ChallengeRecommendation, RecommendationSourceType
from app.models.users import User, UserStatus
from app.repositories.user_repository import (
    PURGE_AFTER_DAYS,
    PURGED_EMAIL_SUFFIX,
    PURGED_NICKNAME,
    UserRepository,
)
from app.services.retention import RetentionService

PASSWORD = "dango1234"
SNAPSHOT = {"policy_version": "v1", "fingerprint": "abc", "answers": ["lunch"], "asked": ["meal"]}


async def make_user(email: str, *, withdrawn_days_ago: int | None) -> User:
    """withdrawn_days_ago 가 None 이면 활성 계정이다."""
    now = datetime.now(config.TIMEZONE)
    return await User.create(
        email=email,
        nickname="탐험가",
        password_hash=hash_password(PASSWORD),
        status=UserStatus.ACTIVE if withdrawn_days_ago is None else UserStatus.WITHDRAWN,
        withdrawn_at=None if withdrawn_days_ago is None else now - timedelta(days=withdrawn_days_ago),
    )


async def make_card(user_id: int) -> ChallengeRecommendation:
    """대화로 만든 추천 한 장. 지우는 대상은 conversation_snapshot 뿐이다."""
    return await ChallengeRecommendation.create(
        user_id=user_id,
        challenge_id=1,
        source_type=RecommendationSourceType.CONVERSATION,
        factor_key="sodium_behavior",
        rank=1,
        recommended_at=datetime.now(config.TIMEZONE),
        conversation_snapshot=SNAPSHOT,
        llm_model_version="llm-test",
    )


class TestPurgeWithdrawn(TestCase):
    async def test_purges_only_after_retention_period(self):
        old = await make_user("old@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS + 1)
        recent = await make_user("recent@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS - 1)
        active = await make_user("active@example.com", withdrawn_days_ago=None)

        result = await RetentionService().purge_withdrawn()

        assert result.purged_user_ids == [old.id]

        purged = await User.get(id=old.id)
        assert purged.email == f"withdrawn-{old.id}{PURGED_EMAIL_SUFFIX}"
        assert purged.nickname == PURGED_NICKNAME
        assert not verify_password(PASSWORD, purged.password_hash)
        # 행은 남는다. 건강기록·예측은 식별정보가 빠진 뒤 통계로 보관한다 (REQ-USER-009)
        assert purged.status is UserStatus.WITHDRAWN
        assert purged.withdrawn_at is not None

        untouched = await User.get(id=recent.id)
        assert untouched.email == "recent@example.com"
        assert untouched.nickname == "탐험가"

        still_active = await User.get(id=active.id)
        assert still_active.email == "active@example.com"
        assert verify_password(PASSWORD, still_active.password_hash)

    async def test_running_twice_changes_nothing(self):
        user = await make_user("twice@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS + 5)
        service = RetentionService()

        first = await service.purge_withdrawn()
        after_first = await User.get(id=user.id)
        second = await service.purge_withdrawn()
        after_second = await User.get(id=user.id)

        assert first.purged_user_ids == [user.id]
        assert second.purged_user_ids == []
        assert after_second.email == after_first.email
        assert after_second.password_hash == after_first.password_hash

    async def test_dry_run_does_not_write(self):
        user = await make_user("dry@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS + 1)

        result = await RetentionService().purge_withdrawn(dry_run=True)

        assert result.purged_user_ids == [user.id]
        kept = await User.get(id=user.id)
        assert kept.email == "dry@example.com"
        assert kept.nickname == "탐험가"

    async def test_now_argument_moves_the_cutoff(self):
        user = await make_user("future@example.com", withdrawn_days_ago=1)
        later = datetime.now(config.TIMEZONE) + timedelta(days=PURGE_AFTER_DAYS)

        before = await RetentionService().purge_withdrawn()
        after = await RetentionService().purge_withdrawn(now=later)

        assert before.purged_user_ids == []
        assert after.purged_user_ids == [user.id]

    async def test_clears_conversation_snapshot_of_purged_accounts_only(self):
        old = await make_user("card-old@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS + 1)
        recent = await make_user("card-recent@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS - 1)
        purged_card = await make_card(old.id)
        kept_card = await make_card(recent.id)

        await RetentionService().purge_withdrawn()

        cleared = await ChallengeRecommendation.get(id=purged_card.id)
        assert cleared.conversation_snapshot is None
        # 지우는 건 이 컬럼뿐이다. 추천 행과 나머지 값은 통계로 남는다 (REQ-CHLG-012)
        assert cleared.factor_key == "sodium_behavior"
        assert cleared.llm_model_version == "llm-test"

        untouched = await ChallengeRecommendation.get(id=kept_card.id)
        assert untouched.conversation_snapshot == SNAPSHOT

    async def test_dry_run_keeps_conversation_snapshot(self):
        user = await make_user("card-dry@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS + 1)
        card = await make_card(user.id)

        await RetentionService().purge_withdrawn(dry_run=True)

        kept = await ChallengeRecommendation.get(id=card.id)
        assert kept.conversation_snapshot == SNAPSHOT

    async def test_rerun_after_a_failed_identifier_purge(self):
        user = await make_user("card-retry@example.com", withdrawn_days_ago=PURGE_AFTER_DAYS + 1)
        card = await make_card(user.id)
        service = RetentionService()

        # 대화 기록을 지운 직후 식별정보 파기가 터지는 상황
        with patch.object(UserRepository, "purge_identifiers", side_effect=RuntimeError("DB 끊김")):
            with pytest.raises(RuntimeError):
                await service.purge_withdrawn()

        half_done = await User.get(id=user.id)
        assert half_done.email == "card-retry@example.com"
        assert (await ChallengeRecommendation.get(id=card.id)).conversation_snapshot is None

        # 식별정보가 아직 그대로라 다음 실행에서 같은 계정이 다시 대상이 된다
        result = await service.purge_withdrawn()

        assert result.purged_user_ids == [user.id]
        purged = await User.get(id=user.id)
        assert purged.email == f"withdrawn-{user.id}{PURGED_EMAIL_SUFFIX}"
        assert purged.nickname == PURGED_NICKNAME
