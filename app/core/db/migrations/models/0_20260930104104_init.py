from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `users` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `email` VARCHAR(255) NOT NULL UNIQUE COMMENT '로그인 이메일',
    `password_hash` VARCHAR(255) NOT NULL COMMENT '해시 저장. 평문·로그 금지 (NFR-SEC-003)',
    `nickname` VARCHAR(50) NOT NULL COMMENT '표시 이름',
    `birth_year` SMALLINT COMMENT '출생연도',
    `sex` VARCHAR(1) COMMENT '성별',
    `height_cm` DECIMAL(4,1) COMMENT '키',
    `motivation_type` VARCHAR(8) NOT NULL COMMENT '보상 유형 (REQ-USER-008)' DEFAULT 'collect',
    `dm_diagnosed` BOOL NOT NULL COMMENT '당뇨 진단 이력 (REQ-USER-007)' DEFAULT 0,
    `htn_diagnosed` BOOL NOT NULL COMMENT '고혈압 진단 이력' DEFAULT 0,
    `dm_medication` BOOL NOT NULL COMMENT '당뇨약·인슐린 복용 여부' DEFAULT 0,
    `htn_medication` BOOL NOT NULL COMMENT '혈압약 복용 여부' DEFAULT 0,
    `total_xp` INT NOT NULL COMMENT '누적 경험치 (REQ-RECO-003)' DEFAULT 0,
    `level` SMALLINT NOT NULL COMMENT '현재 레벨. total_xp에서 파생되나 조회 편의로 함께 저장' DEFAULT 1,
    `disclaimer_agreed_at` DATETIME(6) COMMENT '참고용 고지 동의 일시 (REQ-USER-010)',
    `login_fail_count` SMALLINT NOT NULL COMMENT '연속 로그인 실패 횟수 (REQ-USER-004)' DEFAULT 0,
    `locked_until` DATETIME(6) COMMENT '잠금 해제 시각. 5회 실패 시 10분',
    `status` VARCHAR(9) NOT NULL COMMENT '탈퇴 시 비활성 (REQ-USER-009)' DEFAULT 'active',
    `withdrawn_at` DATETIME(6) COMMENT '탈퇴 시각. +30일에 식별정보 삭제',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4 COMMENT='회원. 테이블 명세서(구글 시트) users 21컬럼 기준이다.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "Yl9VsWrzr/q3TN/+BtwItY8="
)
