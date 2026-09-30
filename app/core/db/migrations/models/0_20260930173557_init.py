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
) CHARACTER SET utf8mb4 COMMENT='회원. 테이블 명세서(구글 시트) users 21컬럼 기준이다.';
CREATE TABLE IF NOT EXISTS `challenges` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(40) NOT NULL UNIQUE,
    `title` VARCHAR(80) NOT NULL,
    `description` VARCHAR(255),
    `category` VARCHAR(8) NOT NULL COMMENT 'ACTIVITY: activity\nDIET: diet\nSMOKING: smoking\nALCOHOL: alcohol\nBODY: body\nSLEEP: sleep',
    `factor_key` VARCHAR(50),
    `goal_type` VARCHAR(8) NOT NULL COMMENT 'BOOLEAN: boolean\nCOUNT: count\nDURATION: duration\nQUANTITY: quantity',
    `target_value` DECIMAL(6,1),
    `unit` VARCHAR(20),
    `daily_target_count` SMALLINT NOT NULL DEFAULT 1,
    `duration_days` SMALLINT NOT NULL DEFAULT 7,
    `verification_type` VARCHAR(6) NOT NULL COMMENT 'MANUAL: manual\nPHOTO: photo\nTIMER: timer\nVALUE: value\nTIME: time\nSYSTEM: system' DEFAULT 'timer',
    `difficulty` VARCHAR(9) NOT NULL COMMENT 'EASY: easy\nNORMAL: normal\nCHALLENGE: challenge' DEFAULT 'easy',
    `relation_type` VARCHAR(10) NOT NULL COMMENT 'DIRECT: direct\nSUPPORTING: supporting\nGENERAL: general' DEFAULT 'supporting',
    `exclude_condition` VARCHAR(200),
    `context_label` VARCHAR(40),
    `manual_fallback_allowed` BOOL NOT NULL DEFAULT 1,
    `context_type` VARCHAR(5) NOT NULL COMMENT 'NONE: none\nMEAL: meal\nEVENT: event' DEFAULT 'none',
    `context_slots` JSON,
    `reward_xp` SMALLINT NOT NULL DEFAULT 0,
    `progress_value` SMALLINT NOT NULL DEFAULT 10,
    `is_enabled` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `monsters` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `code` VARCHAR(20) NOT NULL UNIQUE,
    `no` SMALLINT NOT NULL UNIQUE,
    `name` VARCHAR(30) NOT NULL,
    `title` VARCHAR(60),
    `factor_keys` JSON NOT NULL,
    `disease_scope` VARCHAR(12) NOT NULL COMMENT 'COMMON: common\nDIABETES: diabetes\nHYPERTENSION: hypertension' DEFAULT 'common',
    `default_impact_source` VARCHAR(12) NOT NULL COMMENT 'CONTRIBUTION: contribution\nMEASURED: measured' DEFAULT 'contribution',
    `is_enabled` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_challenges` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `challenge_id` BIGINT NOT NULL,
    `recommendation_id` BIGINT,
    `source_prediction_id` BIGINT,
    `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: active\nCOMPLETED: completed\nABANDONED: abandoned' DEFAULT 'active',
    `start_date` DATE NOT NULL,
    `end_date` DATE NOT NULL,
    `daily_target_count_snapshot` SMALLINT NOT NULL,
    `target_value_snapshot` DECIMAL(6,1),
    `duration_days_snapshot` SMALLINT NOT NULL,
    `completed_at` DATETIME(6),
    `stopped_at` DATETIME(6),
    `stop_reason` VARCHAR(100),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_user_challe_user_id_1d8bec` (`user_id`, `status`)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user_monsters` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `monster_id` BIGINT NOT NULL,
    `impact_score` SMALLINT,
    `state` VARCHAR(16) NOT NULL COMMENT 'RAGE: rage\nCAUTION: caution\nSTABLE: stable\nNOT_CONTRIBUTING: not_contributing\nRESOLVED: resolved\nSEALED: sealed\nUNMEASURED: unmeasured' DEFAULT 'unmeasured',
    `sealed_at` DATETIME(6),
    `resolved_at` DATETIME(6),
    `reawakened_at` DATETIME(6),
    `seal_count` SMALLINT NOT NULL DEFAULT 0,
    `impact_source` VARCHAR(12) NOT NULL COMMENT 'CONTRIBUTION: contribution\nMEASURED: measured\nGLOBAL: global' DEFAULT 'contribution',
    `last_prediction_id` BIGINT,
    `last_health_record_id` BIGINT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `weekly_progress` SMALLINT NOT NULL DEFAULT 0,
    `progress_week_start` DATE,
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_user_monste_user_id_b3b3a2` (`user_id`, `monster_id`)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "+RtzmHJltYakMBWHPu9Cn5z+0Oef/wNg4ON0"
)
