from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `health_records` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `recorded_at` DATETIME(6) NOT NULL COMMENT '입력 시점. 덮어쓰지 않고 누적',
    `input_mode` VARCHAR(6) NOT NULL COMMENT 'SIMPLE: simple\nDETAIL: detail\nDAILY: daily' DEFAULT 'simple',
    `weight_kg` DECIMAL(4,1),
    `waist_cm` DECIMAL(4,1),
    `bmi` DECIMAL(4,1),
    `smoking_current` BOOL,
    `alcohol_frequency` SMALLINT,
    `alcohol_amount` SMALLINT,
    `walking_days` SMALLINT COMMENT '주당 0~7',
    `walking_minutes` SMALLINT,
    `strength_days` SMALLINT COMMENT '주당 0~7',
    `sitting_minutes` SMALLINT,
    `family_history_dm` BOOL,
    `family_history_htn` BOOL,
    `dining_out_freq` SMALLINT COMMENT '외식 빈도 1~7. 1 거의 매일 2회+, 7 거의 안 함',
    `sbp` SMALLINT,
    `dbp` SMALLINT,
    `fasting_glucose` SMALLINT,
    `hba1c` DECIMAL(3,1),
    `triglyceride` SMALLINT,
    `hdl` SMALLINT,
    `total_cholesterol` SMALLINT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_health_reco_user_id_a8c11a` (`user_id`, `recorded_at`)
) CHARACTER SET utf8mb4 COMMENT='건강정보 기록. 테이블 명세서 health_records 26컬럼 기준이다.';
        CREATE TABLE IF NOT EXISTS `user_attack_cycles` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `target_user_monster_id` BIGINT NOT NULL COMMENT '같은 사용자 소유의 공략 대상',
    `start_date` DATE COMMENT 'draft에서는 NULL. KST D0',
    `end_date` DATE COMMENT 'start_date+27. 마지막 수행 가능 날짜 포함',
    `status` VARCHAR(9) NOT NULL COMMENT 'DRAFT: draft\nACTIVE: active\nCOMPLETED: completed\nABANDONED: abandoned' DEFAULT 'draft',
    `extra_added_count` SMALLINT NOT NULL COMMENT '2주차 이후 추가 횟수 0 또는 1' DEFAULT 0,
    `policy_version` VARCHAR(32) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    KEY `idx_user_attack_user_id_f5bd33` (`user_id`, `status`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `user_challenge_occurrences` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `user_challenge_id` BIGINT NOT NULL,
    `scheduled_date` DATE NOT NULL COMMENT 'KST 달력 날짜',
    `slot_code` VARCHAR(20) NOT NULL COMMENT 'lunch·dinner 등. 독립 회차는 빈 문자열. NULL은 유니크가 걸리지 않아 쓰지 않는다' DEFAULT '',
    `sequence_no` SMALLINT NOT NULL COMMENT '같은 날 독립 회차 번호' DEFAULT 1,
    `status` VARCHAR(9) NOT NULL COMMENT 'completed만 수행률 분자. skipped·missed는 분모에만 남는다' DEFAULT 'planned',
    `completed_log_id` BIGINT UNIQUE COMMENT '이 기회를 인정한 수행 기록',
    `completed_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY `uid_user_challe_user_ch_618f4e` (`user_challenge_id`, `scheduled_date`, `slot_code`, `sequence_no`),
    KEY `idx_user_challe_schedul_9cf6d1` (`scheduled_date`),
    KEY `idx_user_challe_user_ch_2ac5f8` (`user_challenge_id`, `status`)
) CHARACTER SET utf8mb4;
        ALTER TABLE `challenges` ADD INDEX `idx_challenges_factor__8691e7` (`factor_key`, `is_enabled`);
        ALTER TABLE `challenges` ADD `personalization_policy` JSON COMMENT 'NULL이면 기존 고정 원형';
        ALTER TABLE `challenges` ADD `context_priority` SMALLINT COMMENT '같은 factor 안의 후보 순위';
        ALTER TABLE `challenge_recommendations` ADD `conversation_snapshot` JSON COMMENT '개인정보는 담지 않는다';
        ALTER TABLE `challenge_recommendations` ADD `proposed_goal` JSON COMMENT '서버 검증을 통과한 개인 목표';
        ALTER TABLE `challenge_recommendations` ADD `llm_model_version` VARCHAR(32);
        ALTER TABLE `challenge_recommendations` ADD `evidence_card_ids` JSON COMMENT '승인 근거 카드 ID 배열';
        ALTER TABLE `challenge_recommendations` ADD `cycle_id` BIGINT COMMENT '추천을 만든 주기. 지난 주기 추천으로 시작 금지';
        ALTER TABLE `challenge_recommendations` MODIFY COLUMN `source_type` VARCHAR(19) NOT NULL COMMENT 'PREDICTION_PERSONAL: prediction_personal\nDIAGNOSIS_GLOBAL: diagnosis_global\nCONVERSATION: conversation';
        ALTER TABLE `user_challenges` ADD `summary_computed_at` DATETIME(6);
        ALTER TABLE `user_challenges` ADD `goal_config_snapshot` JSON COMMENT '예정 기회 배열은 담지 않는다';
        ALTER TABLE `user_challenges` ADD `summary_policy_version` VARCHAR(20);
        ALTER TABLE `user_challenges` ADD `habit_established` BOOL COMMENT '1단계는 판정 유예. NULL=미평가';
        ALTER TABLE `user_challenges` ADD `planned_occurrence_count` SMALLINT COMMENT '종료 시점 예정 기회 수. 수행률 분모';
        ALTER TABLE `user_challenges` ADD `completion_rate` DECIMAL(5,4) COMMENT '분모 0이면 NULL';
        ALTER TABLE `user_challenges` ADD `cycle_id` BIGINT COMMENT '레거시·주기 밖 미션만 NULL';
        ALTER TABLE `user_challenges` ADD `completed_occurrence_count` SMALLINT COMMENT '종료 시점 인정 완료 기회 수';
        ALTER TABLE `user_challenges` MODIFY COLUMN `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: active\nCOMPLETED: completed\nGRADUATED: graduated\nABANDONED: abandoned' DEFAULT 'active';
        ALTER TABLE `user_challenges` ADD INDEX `idx_user_challe_cycle_i_f7c158` (`cycle_id`);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `user_challenges` DROP INDEX `idx_user_challe_cycle_i_f7c158`;
        ALTER TABLE `challenges` DROP INDEX `idx_challenges_factor__8691e7`;
        ALTER TABLE `challenges` DROP COLUMN `personalization_policy`;
        ALTER TABLE `challenges` DROP COLUMN `context_priority`;
        ALTER TABLE `user_challenges` DROP COLUMN `summary_computed_at`;
        ALTER TABLE `user_challenges` DROP COLUMN `goal_config_snapshot`;
        ALTER TABLE `user_challenges` DROP COLUMN `summary_policy_version`;
        ALTER TABLE `user_challenges` DROP COLUMN `habit_established`;
        ALTER TABLE `user_challenges` DROP COLUMN `planned_occurrence_count`;
        ALTER TABLE `user_challenges` DROP COLUMN `completion_rate`;
        ALTER TABLE `user_challenges` DROP COLUMN `cycle_id`;
        ALTER TABLE `user_challenges` DROP COLUMN `completed_occurrence_count`;
        ALTER TABLE `user_challenges` MODIFY COLUMN `status` VARCHAR(9) NOT NULL COMMENT 'ACTIVE: active\nCOMPLETED: completed\nABANDONED: abandoned' DEFAULT 'active';
        ALTER TABLE `challenge_recommendations` DROP COLUMN `conversation_snapshot`;
        ALTER TABLE `challenge_recommendations` DROP COLUMN `proposed_goal`;
        ALTER TABLE `challenge_recommendations` DROP COLUMN `llm_model_version`;
        ALTER TABLE `challenge_recommendations` DROP COLUMN `evidence_card_ids`;
        ALTER TABLE `challenge_recommendations` DROP COLUMN `cycle_id`;
        ALTER TABLE `challenge_recommendations` MODIFY COLUMN `source_type` VARCHAR(19) NOT NULL COMMENT 'PREDICTION_PERSONAL: prediction_personal\nDIAGNOSIS_GLOBAL: diagnosis_global';
        DROP TABLE IF EXISTS `user_attack_cycles`;
        DROP TABLE IF EXISTS `health_records`;
        DROP TABLE IF EXISTS `user_challenge_occurrences`;"""


MODELS_STATE = (
    "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"
    "cYUkQnqcGsmRaCANUuzj6JZcsJUql//+f+Ny0cw="
)
