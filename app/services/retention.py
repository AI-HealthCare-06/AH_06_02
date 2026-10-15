"""탈퇴 계정 보관 기간 처리 (REQ-USER-009).

탈퇴하면 USER-05 가 status 를 withdrawn 으로 바꾸고 행은 남긴다.
그 뒤 PURGE_AFTER_DAYS 가 지난 계정의 식별정보를 지우는 것이 이 서비스다.
건강기록·예측 결과는 지우지 않는다. 식별정보가 빠진 뒤 통계 목적으로 남는다.

대화형 추천 기록(challenge_recommendations.conversation_snapshot)도 같이 비운다.
D 테이블이지만 지우는 시점이 이 배치라 table-spec 에서 A 작업으로 잡혀 있다 (REQ-CHLG-012).

챌린지 인증 사진도 같은 시점에 지운다 (REQ-USER-009 · NFR-SEC-005). 파일은 HLTH-03 저장소의
EvidenceService 가 지우고, 참조값 challenge_logs.evidence_url 은 비운다. 수행 기록 자체는 남긴다.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime

from app.core.utils.security import hash_password
from app.models.challenges import ChallengeLog, ChallengeRecommendation, UserChallenge
from app.repositories.user_repository import UserRepository
from app.services.evidence import EvidenceService


@dataclass(frozen=True)
class PurgeResult:
    """파기한 계정 id 목록. 멱등이라 다시 돌리면 빈 목록이 나온다."""

    purged_user_ids: list[int]

    @property
    def count(self) -> int:
        return len(self.purged_user_ids)


class RetentionService:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.evidence = EvidenceService()

    async def purge_withdrawn(self, now: datetime | None = None, dry_run: bool = False) -> PurgeResult:
        """기한이 지난 탈퇴 계정의 이메일·닉네임·비밀번호 해시와 대화 기록·인증 사진을 지운다.

        now 를 주면 그 시각 기준으로 본다. 테스트와 수동 실행에서 쓴다.
        dry_run 이면 대상만 세고 쓰지 않는다.
        """
        targets = await self.users.find_purgeable(now)
        if dry_run:
            return PurgeResult([user.id for user in targets])

        purged: list[int] = []
        for user in targets:
            # 식별정보보다 먼저 지운다. 중간에 멈춰도 계정이 아직 대상이라 다음 실행에서 다시 걸린다
            await ChallengeRecommendation.filter(user_id=user.id).update(conversation_snapshot=None)
            self.evidence.delete_user_photos(user.id)
            missions = await UserChallenge.filter(user_id=user.id).values_list("id", flat=True)
            await ChallengeLog.filter(user_challenge_id__in=missions, evidence_url__isnull=False).update(
                evidence_url=None
            )
            # 아무도 모르는 값이라 이 해시로는 로그인할 수 없다. 컬럼 형식은 그대로 둔다
            await self.users.purge_identifiers(user, hash_password(secrets.token_urlsafe(32)))
            purged.append(user.id)
        return PurgeResult(purged)
