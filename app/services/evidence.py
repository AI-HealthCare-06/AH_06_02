"""HLTH-03 챌린지 PHOTO 증빙 업로드 서비스."""

import re
import uuid
import warnings
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core import config
from app.core.errors import AppError, ErrorCode
from app.models.challenges import (
    AttackCycleStatus,
    Challenge,
    UserAttackCycle,
    UserChallenge,
    UserChallengeStatus,
    VerificationType,
)
from app.models.users import User

# 허용된 이미지 타입과 최대 크기 (10 MiB)
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_FILE_SIZE = 10 * 1024 * 1024

# 비공개 저장 경로
MEDIA_EVIDENCE_DIR = Path("/app/media/evidence")


class EvidenceService:
    """챌린지 증빙 사진 업로드 서비스."""

    async def verify_challenge_ownership(self, user: User, user_challenge_id: int) -> UserChallenge:
        """사진 참조값의 사용자·미션 소유권을 확인한다.

        본인의 활성 PHOTO 챌린지인지 검증한다.
        """
        challenge = await UserChallenge.get_or_none(id=user_challenge_id)
        if not challenge:
            raise AppError(ErrorCode.CHLG_NOT_FOUND, "해당 챌린지를 찾을 수 없습니다.")
        if challenge.user_id != user.id:
            raise AppError(ErrorCode.FORBIDDEN, "본인의 챌린지가 아닙니다.")
        if challenge.status != UserChallengeStatus.ACTIVE:
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE, "진행 중인 챌린지가 아닙니다.")
        master = await Challenge.get_or_none(id=challenge.challenge_id)
        today = datetime.now(config.TIMEZONE).date()
        if master is None or master.verification_type != VerificationType.PHOTO:
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE, "사진 인증 챌린지가 아닙니다.")
        if not challenge.start_date <= today <= challenge.end_date:
            raise AppError(ErrorCode.CHLG_NOT_ACTIVE, "수행 기간이 아닙니다.")
        if challenge.cycle_id is not None:
            cycle = await UserAttackCycle.get_or_none(id=challenge.cycle_id, user_id=user.id)
            if (
                cycle is None
                or cycle.status != AttackCycleStatus.ACTIVE
                or cycle.end_date is None
                or today > cycle.end_date
            ):
                raise AppError(ErrorCode.CHLG_NOT_ACTIVE)
        return challenge

    async def upload_photo(self, user: User, photo: UploadFile, user_challenge_id: int) -> tuple[str, datetime]:
        """HLTH-03. 챌린지 PHOTO 증빙 업로드.

        사진을 비공개 저장하고 evidence_url 참조값을 반환한다.
        AI 분석·음식 성분 추정은 하지 않는다.
        """
        # 소유권 확인
        await self.verify_challenge_ownership(user, user_challenge_id)

        # 파일 형식 검증
        if photo.content_type not in ALLOWED_CONTENT_TYPES:
            raise AppError(ErrorCode.VALIDATION_ERROR, "JPEG 또는 PNG 형식만 업로드할 수 있습니다.")

        # 파일 크기 검증
        content = await photo.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise AppError(ErrorCode.VALIDATION_ERROR, "파일 크기는 10MB를 초과할 수 없습니다.")
        if not content:
            raise AppError(ErrorCode.VALIDATION_ERROR, "빈 파일은 업로드할 수 없습니다.")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    expected = "JPEG" if photo.content_type == "image/jpeg" else "PNG"
                    if image.format != expected:
                        raise ValueError("파일 형식 불일치")
                    image.verify()
        except (
            UnidentifiedImageError,
            SyntaxError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise AppError(ErrorCode.VALIDATION_ERROR, "올바른 JPEG·PNG 사진을 선택해주세요.") from exc

        # 비공개 저장
        MEDIA_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        ext = "jpg" if photo.content_type == "image/jpeg" else "png"
        filename = f"{user.id}_{user_challenge_id}_{uuid.uuid4().hex}.{ext}"
        filepath = MEDIA_EVIDENCE_DIR / filename
        filepath.write_bytes(content)

        # evidence_url은 공개 URL이 아닌 비공개 참조값
        evidence_url = f"evidence://{filename}"
        uploaded_at = datetime.now(config.TIMEZONE)

        return evidence_url, uploaded_at

    async def verify_reference(self, user_id: int, user_challenge_id: int, reference: str | None) -> bool:
        """D 수행 기록에서 사용한다. 사용자·미션이 일치하는 실제 비공개 파일만 인정한다."""
        if not isinstance(reference, str):
            return False
        pattern = rf"evidence://({user_id}_{user_challenge_id}_[0-9a-f]{{32}}\.(?:jpg|png))"
        match = re.fullmatch(pattern, reference)
        if match is None:
            return False
        path = MEDIA_EVIDENCE_DIR / match.group(1)
        if path.is_symlink() or not path.is_file():
            return False
        return 0 < path.stat().st_size <= MAX_FILE_SIZE
