"""사진 업로드와 비공개 참조값 검증의 HTTP 계약."""

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from PIL import Image
from tortoise.contrib.test import TestCase

from app.core import config
from app.dependencies.security import get_request_user
from app.main import app
from app.models.challenges import Challenge, ChallengeLog, UserChallenge, UserChallengeOccurrence
from app.models.users import User
from app.services.attack_cycles import today_kst
from app.services.evidence import EvidenceService


class TestEvidenceApis(TestCase):
    async def test_upload_rejects_non_photo_mission_and_forged_jpeg(self):
        user = await User.create(email="photo@example.com", nickname="사진", password_hash="x")
        card = await Challenge.create(
            code="photo-test", title="검증", category="diet", goal_type="boolean", verification_type="manual"
        )
        day = today_kst()
        mission = await UserChallenge.create(
            user_id=user.id,
            challenge_id=card.id,
            start_date=day,
            end_date=day + timedelta(days=27),
            duration_days_snapshot=28,
            daily_target_count_snapshot=1,
        )
        app.dependency_overrides[get_request_user] = lambda: user
        try:
            with TemporaryDirectory() as directory, patch("app.services.evidence.MEDIA_EVIDENCE_DIR", Path(directory)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    result = await client.post(
                        "/api/v1/evidence/photos",
                        data={"user_challenge_id": mission.id},
                        files={"photo": ("fake.jpg", b"not-an-image", "image/jpeg")},
                    )
                assert result.status_code == 409
        finally:
            app.dependency_overrides.clear()

    async def test_valid_upload_binds_reference_to_user_and_mission(self):
        user = await User.create(email="valid-photo@example.com", nickname="사진", password_hash="x")
        card = await Challenge.create(
            code="valid-photo", title="검증", category="diet", goal_type="boolean", verification_type="photo"
        )
        day = today_kst()
        mission = await UserChallenge.create(
            user_id=user.id,
            challenge_id=card.id,
            start_date=day,
            end_date=day + timedelta(days=27),
            duration_days_snapshot=28,
            daily_target_count_snapshot=1,
        )
        content = BytesIO()
        Image.new("RGB", (1, 1)).save(content, format="PNG")
        app.dependency_overrides[get_request_user] = lambda: user
        try:
            with TemporaryDirectory() as directory, patch("app.services.evidence.MEDIA_EVIDENCE_DIR", Path(directory)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    result = await client.post(
                        "/api/v1/evidence/photos",
                        data={"user_challenge_id": mission.id},
                        files={"photo": ("photo.png", content.getvalue(), "image/png")},
                    )
                    assert result.status_code == 201
                    reference = result.json()["data"]["evidence_url"]
                    service = EvidenceService()
                    assert await service.verify_reference(user.id, mission.id, reference)
                    await UserChallengeOccurrence.create(
                        user_challenge_id=mission.id, scheduled_date=day, sequence_no=1
                    )
                    body = {
                        "occurred_at": datetime.now(config.TIMEZONE).isoformat(),
                        "verification_method": "photo",
                        "evidence_url": "evidence://forged",
                    }
                    rejected = await client.post(f"/api/v1/user-challenges/{mission.id}/logs", json=body)
                    assert rejected.status_code == 422
                    assert rejected.json()["error"]["code"] == "CHLG_VERIFICATION_FAILED"
                    assert await ChallengeLog.all().count() == 0
                    body["evidence_url"] = reference
                    accepted = await client.post(f"/api/v1/user-challenges/{mission.id}/logs", json=body)
                    assert accepted.status_code == 201
                    assert await ChallengeLog.all().count() == 1

                    assert not await service.verify_reference(user.id + 1, mission.id, reference)
                    assert not await service.verify_reference(user.id, mission.id + 1, reference)
                    assert not await service.verify_reference(user.id, mission.id, "evidence://../secret")
                    bad = await client.post(
                        "/api/v1/evidence/photos",
                        data={"user_challenge_id": mission.id},
                        files={"photo": ("fake.png", b"not-an-image", "image/png")},
                    )
                    assert bad.status_code == 400
                    (Path(directory) / reference.removeprefix("evidence://")).unlink()
                    assert not await service.verify_reference(user.id, mission.id, reference)
        finally:
            app.dependency_overrides.clear()
