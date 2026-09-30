from datetime import datetime
from enum import StrEnum

from tortoise import fields, models


class Sex(StrEnum):
    MALE = "M"
    FEMALE = "F"


class MotivationType(StrEnum):
    COLLECT = "collect"
    GROW = "grow"
    DECORATE = "decorate"


class UserStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class User(models.Model):
    """회원. 테이블 명세서(구글 시트) users 21컬럼 기준이다.

    이 테이블은 A(배수빈)만 쓴다. 다른 파트는 읽기만 하고,
    경험치 지급은 A가 제공하는 grant_xp()를 호출한다.
    """

    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255, unique=True, description="로그인 이메일")
    password_hash = fields.CharField(max_length=255, description="해시 저장. 평문·로그 금지 (NFR-SEC-003)")
    nickname = fields.CharField(max_length=50, description="표시 이름")

    # 나이는 조회 시 계산한다. 나이를 직접 저장하면 해가 바뀔 때 틀어진다
    birth_year = fields.SmallIntField(null=True, description="출생연도")
    sex = fields.CharEnumField(enum_type=Sex, max_length=1, null=True, description="성별")
    height_cm = fields.DecimalField(max_digits=4, decimal_places=1, null=True, description="키")

    motivation_type = fields.CharEnumField(
        enum_type=MotivationType,
        max_length=8,
        default=MotivationType.COLLECT,
        description="보상 유형 (REQ-USER-008)",
    )

    dm_diagnosed = fields.BooleanField(default=False, description="당뇨 진단 이력 (REQ-USER-007)")
    htn_diagnosed = fields.BooleanField(default=False, description="고혈압 진단 이력")
    dm_medication = fields.BooleanField(default=False, description="당뇨약·인슐린 복용 여부")
    htn_medication = fields.BooleanField(default=False, description="혈압약 복용 여부")

    total_xp = fields.IntField(default=0, description="누적 경험치 (REQ-RECO-003)")
    level = fields.SmallIntField(default=1, description="현재 레벨. total_xp에서 파생되나 조회 편의로 함께 저장")

    disclaimer_agreed_at: datetime | None = fields.DatetimeField(
        null=True, description="참고용 고지 동의 일시 (REQ-USER-010)"
    )

    login_fail_count = fields.SmallIntField(default=0, description="연속 로그인 실패 횟수 (REQ-USER-004)")
    locked_until: datetime | None = fields.DatetimeField(null=True, description="잠금 해제 시각. 5회 실패 시 10분")

    login_fail_count = fields.SmallIntField(default=0, description="연속 로그인 실패 횟수 (REQ-USER-004)")
    locked_until = fields.DatetimeField(null=True, description="잠금 해제 시각. 5회 실패 시 10분")

    status = fields.CharEnumField(
        enum_type=UserStatus,
        max_length=9,
        default=UserStatus.ACTIVE,
        description="탈퇴 시 비활성 (REQ-USER-009)",
    )
    withdrawn_at: datetime | None = fields.DatetimeField(null=True, description="탈퇴 시각. +30일에 식별정보 삭제")

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
