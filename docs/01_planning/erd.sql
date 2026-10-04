-- 당고킬러 (AH_06_02) 스키마
-- 2026.10.04 · 당고킬러_테이블명세서 기준 · 14테이블 222컬럼 FK23
--
-- 시트에 제거안으로 표시된 컬럼 세 개는 넣지 않았다.
--   user_monsters.is_target                     공략 중 여부는 active 주기와 대상을 조인해 계산
--   user_challenges.cycle_week                  주기 시작일과 KST 기준일로 계산
--   user_challenges.completion_summary_snapshot 종료 집계 컬럼 다섯 개로 대체
--
-- 시트에 없고 여기서만 추가한 것
--   user_attack_cycles.active_user_id           사용자당 active 주기를 하나로 강제하는 생성 컬럼
--   user_monsters (id, user_id) 유니크 + 공략 주기의 복합 FK  대상 캐릭터 소유권 강제
--
-- 시각은 UTC DATETIME으로 저장하고 화면에서 KST로 바꾼다.
-- KST 달력 날짜를 뜻하는 필드는 DATE로 둔다. UTC 변환으로 하루를 밀지 않는다.
-- Tortoise ORM은 ENUM을 VARCHAR로, TINYINT를 SMALLINT로 만든다.
-- 이 파일은 설계 기준이고 실제 생성은 aerich migration을 따른다.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------- 회원

CREATE TABLE users (
  id                   BIGINT       NOT NULL AUTO_INCREMENT,
  email                VARCHAR(255) NOT NULL,
  password_hash        VARCHAR(255) NOT NULL COMMENT '해시 저장. 평문·로그 금지',
  nickname             VARCHAR(50)  NOT NULL,
  birth_year           SMALLINT     NULL COMMENT '나이는 조회 시 계산',
  sex                  ENUM('M','F') NULL,
  height_cm            DECIMAL(4,1) NULL,
  motivation_type      ENUM('collect','grow','decorate') NOT NULL DEFAULT 'collect',
  dm_diagnosed         BOOLEAN      NOT NULL DEFAULT FALSE,
  htn_diagnosed        BOOLEAN      NOT NULL DEFAULT FALSE,
  dm_medication        BOOLEAN      NOT NULL DEFAULT FALSE,
  htn_medication       BOOLEAN      NOT NULL DEFAULT FALSE,
  total_xp             INT          NOT NULL DEFAULT 0,
  level                SMALLINT     NOT NULL DEFAULT 1,
  disclaimer_agreed_at DATETIME     NULL,
  login_fail_count     TINYINT      NOT NULL DEFAULT 0,
  locked_until         DATETIME     NULL COMMENT '5회 실패 시 10분',
  status               ENUM('active','withdrawn') NOT NULL DEFAULT 'active',
  withdrawn_at         DATETIME     NULL COMMENT '+30일에 식별정보 삭제',
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='회원';

-- ---------------------------------------------------------------- 건강정보

CREATE TABLE health_records (
  id                 BIGINT   NOT NULL AUTO_INCREMENT,
  user_id            BIGINT   NOT NULL,
  recorded_at        DATETIME NOT NULL COMMENT '입력 시점. 덮어쓰지 않고 누적',
  input_mode         ENUM('simple','detail','daily') NOT NULL DEFAULT 'simple',
  weight_kg          DECIMAL(4,1) NULL,
  waist_cm           DECIMAL(4,1) NULL,
  bmi                DECIMAL(4,1) NULL,
  smoking_current    BOOLEAN  NULL,
  alcohol_frequency  TINYINT  NULL,
  alcohol_amount     TINYINT  NULL,
  walking_days       TINYINT  NULL COMMENT '주당 0~7',
  walking_minutes    SMALLINT NULL,
  strength_days      TINYINT  NULL COMMENT '주당 0~7',
  sitting_minutes    SMALLINT NULL,
  family_history_dm  BOOLEAN  NULL,
  family_history_htn BOOLEAN  NULL,
  dining_out_freq    TINYINT  NULL COMMENT '외식 빈도 1~7. 1 거의 매일 2회+, 7 거의 안 함',
  sbp                SMALLINT NULL,
  dbp                SMALLINT NULL,
  fasting_glucose    SMALLINT NULL,
  hba1c              DECIMAL(3,1) NULL,
  triglyceride       SMALLINT NULL,
  hdl                SMALLINT NULL,
  total_cholesterol  SMALLINT NULL,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_hr_user_recorded (user_id, recorded_at),
  CONSTRAINT fk_hr_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='건강정보 기록';

-- ---------------------------------------------------------------- 예측

CREATE TABLE predictions (
  id               BIGINT      NOT NULL AUTO_INCREMENT,
  user_id          BIGINT      NOT NULL,
  health_record_id BIGINT      NOT NULL,
  job_id           VARCHAR(64) NOT NULL COMMENT '비동기 작업 식별자',
  status           ENUM('pending','done','failed') NOT NULL DEFAULT 'pending',
  dm_probability   DECIMAL(5,4) NULL COMMENT '0~1. 화면에서 %로 변환',
  dm_grade         ENUM('low','caution','high') NULL,
  htn_probability  DECIMAL(5,4) NULL,
  htn_grade        ENUM('low','caution','high') NULL,
  metabolic_count  TINYINT     NULL COMMENT '대사증후군 해당 지표 수 0~5',
  model_version    VARCHAR(64) NOT NULL COMMENT "실제 값 예시 knhanes-ix-hypertension-base_sodium-s42 는 39자",
  input_snapshot   JSON        NULL COMMENT '전처리 전 canonical 값·단위·결측 여부',
  predicted_at     DATETIME    NULL,
  created_at       DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pred_job (job_id),
  KEY ix_pred_user_created (user_id, created_at),
  CONSTRAINT fk_pred_user   FOREIGN KEY (user_id)          REFERENCES users (id),
  CONSTRAINT fk_pred_record FOREIGN KEY (health_record_id) REFERENCES health_records (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='예측 결과';

CREATE TABLE prediction_contributions (
  id            BIGINT      NOT NULL AUTO_INCREMENT,
  prediction_id BIGINT      NOT NULL,
  disease       ENUM('diabetes','hypertension') NOT NULL,
  factor_key    VARCHAR(50) NOT NULL,
  contribution  DECIMAL(8,5) NOT NULL COMMENT '정규화 전 signed grouped SHAP',
  direction     ENUM('increase','decrease') NOT NULL COMMENT '0은 decrease',
  rank          TINYINT     NOT NULL COMMENT '질환별 절대 기여도 내림차순',
  created_at    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_pc_pred_disease_rank (prediction_id, disease, rank),
  CONSTRAINT fk_pc_pred FOREIGN KEY (prediction_id) REFERENCES predictions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='기여요인';

-- ---------------------------------------------------------------- 캐릭터

CREATE TABLE monsters (
  id                    BIGINT      NOT NULL AUTO_INCREMENT,
  code                  VARCHAR(20) NOT NULL COMMENT 'spike / alde / cotinine / viscera / sodi',
  no                    TINYINT     NOT NULL COMMENT '도감 번호 1~5',
  name                  VARCHAR(30) NOT NULL,
  title                 VARCHAR(60) NULL,
  factor_keys           JSON        NOT NULL COMMENT '연결된 factor_key 배열',
  disease_scope         ENUM('common','diabetes','hypertension') NOT NULL DEFAULT 'common',
  default_impact_source ENUM('contribution','measured') NOT NULL DEFAULT 'contribution',
  is_enabled            BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at            DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_monsters_code (code),
  UNIQUE KEY uq_monsters_no (no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='캐릭터 마스터';

CREATE TABLE user_monsters (
  id                     BIGINT   NOT NULL AUTO_INCREMENT,
  user_id                BIGINT   NOT NULL,
  monster_id             BIGINT   NOT NULL,
  impact_score           TINYINT  NULL COMMENT '위협도 0~100. NULL이면 미측정',
  state                  ENUM('rage','caution','stable','not_contributing','resolved','sealed','unmeasured')
                           NOT NULL DEFAULT 'unmeasured',
  sealed_at              DATETIME NULL,
  resolved_at            DATETIME NULL,
  reawakened_at          DATETIME NULL,
  seal_count             SMALLINT NOT NULL DEFAULT 0,
  impact_source          ENUM('contribution','measured','global') NOT NULL DEFAULT 'contribution',
  last_prediction_id     BIGINT   NULL,
  last_health_record_id  BIGINT   NULL,
  weekly_progress        SMALLINT NOT NULL DEFAULT 0 COMMENT '주간 공략 점수. 상한 100',
  progress_week_start    DATE     NULL COMMENT '월요일 00:00 KST에 초기화',
  created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_um_user_monster (user_id, monster_id),
  -- 공략 주기가 같은 사용자의 캐릭터만 대상으로 삼도록 복합 FK의 참조 대상이 된다
  UNIQUE KEY uq_um_id_user (id, user_id),
  CONSTRAINT fk_um_user    FOREIGN KEY (user_id)               REFERENCES users (id),
  CONSTRAINT fk_um_monster FOREIGN KEY (monster_id)            REFERENCES monsters (id),
  CONSTRAINT fk_um_pred    FOREIGN KEY (last_prediction_id)    REFERENCES predictions (id),
  CONSTRAINT fk_um_record  FOREIGN KEY (last_health_record_id) REFERENCES health_records (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='사용자 캐릭터 상태';

-- ---------------------------------------------------------------- 공략 주기

CREATE TABLE user_attack_cycles (
  id                     BIGINT      NOT NULL AUTO_INCREMENT,
  user_id                BIGINT      NOT NULL,
  target_user_monster_id BIGINT      NOT NULL COMMENT '같은 사용자 소유의 공략 대상',
  start_date             DATE        NULL COMMENT 'draft에서는 NULL. KST D0',
  end_date               DATE        NULL COMMENT 'start_date+27. 마지막 수행 가능 날짜 포함',
  status                 ENUM('draft','active','completed','abandoned') NOT NULL DEFAULT 'draft',
  extra_added_count      TINYINT     NOT NULL DEFAULT 0 COMMENT '2주차 이후 추가 횟수 0 또는 1',
  policy_version         VARCHAR(32) NOT NULL,
  -- status가 active일 때만 user_id를 담는다. NULL끼리는 충돌하지 않으므로
  -- 종료 이력은 여러 개 남고 active 주기만 사용자당 하나로 강제된다.
  active_user_id         BIGINT GENERATED ALWAYS AS (IF(status = 'active', user_id, NULL)) STORED,
  created_at             DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at             DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_uac_active (active_user_id),
  KEY ix_uac_user_status (user_id, status),
  CONSTRAINT fk_uac_user   FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_uac_target FOREIGN KEY (target_user_monster_id, user_id)
                           REFERENCES user_monsters (id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='사용자 공략 주기';

-- draft도 사용자당 하나로 막으려면 같은 방식의 컬럼을 하나 더 둔다.
--   draft_user_id BIGINT GENERATED ALWAYS AS (IF(status = 'draft', user_id, NULL)) STORED,
--   UNIQUE KEY uq_uac_draft (draft_user_id)

-- ---------------------------------------------------------------- 챌린지

CREATE TABLE challenges (
  id                      BIGINT       NOT NULL AUTO_INCREMENT,
  code                    VARCHAR(40)  NOT NULL,
  title                   VARCHAR(80)  NOT NULL,
  description             VARCHAR(255) NULL,
  category                ENUM('activity','diet','smoking','alcohol','body','sleep') NOT NULL,
  factor_key              VARCHAR(50)  NULL COMMENT 'NULL이면 보너스 챌린지. 공략 점수는 쌓지 않음',
  goal_type               ENUM('boolean','count','duration','quantity') NOT NULL,
  target_value            DECIMAL(6,1) NULL COMMENT '고정 원형의 1회 기본값',
  unit                    VARCHAR(20)  NULL,
  daily_target_count      TINYINT      NOT NULL DEFAULT 1,
  duration_days           SMALLINT     NOT NULL DEFAULT 7 COMMENT '레거시 고정 미션용. 주기 미션은 주기 경계에서 종료',
  verification_type       ENUM('manual','photo','timer','value','time','system') NOT NULL DEFAULT 'timer',
  difficulty              ENUM('easy','normal','challenge') NOT NULL DEFAULT 'easy',
  relation_type           ENUM('direct','supporting','general') NOT NULL DEFAULT 'supporting',
  exclude_condition       VARCHAR(200) NULL,
  context_label           VARCHAR(40)  NULL,
  manual_fallback_allowed BOOLEAN      NOT NULL DEFAULT TRUE,
  context_type            ENUM('none','meal','event') NOT NULL DEFAULT 'none',
  context_slots           JSON         NULL COMMENT "['lunch','dinner']",
  reward_xp               SMALLINT     NOT NULL DEFAULT 0,
  progress_value          SMALLINT     NOT NULL DEFAULT 10 COMMENT '1회당 공략 점수',
  is_enabled              BOOLEAN      NOT NULL DEFAULT TRUE,
  safety_check_required   BOOLEAN      NOT NULL DEFAULT FALSE,
  context_priority        TINYINT      NULL COMMENT '같은 factor 안의 후보 순위',
  personalization_policy  JSON         NULL COMMENT 'NULL이면 기존 고정 원형',
  created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ch_code (code),
  KEY ix_ch_factor_enabled (factor_key, is_enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='챌린지 마스터';

CREATE TABLE challenge_recommendations (
  id                       BIGINT      NOT NULL AUTO_INCREMENT,
  user_id                  BIGINT      NOT NULL,
  challenge_id             BIGINT      NOT NULL,
  cycle_id                 BIGINT      NULL COMMENT '추천을 만든 주기. 지난 주기 추천으로 시작 금지',
  source_type              ENUM('prediction_personal','diagnosis_global','conversation') NOT NULL,
  factor_key               VARCHAR(50) NOT NULL,
  factor_score             DECIMAL(8,5) NULL,
  rank                     TINYINT     NOT NULL COMMENT '카드 순위 1~3',
  recommended_at           DATETIME    NOT NULL,
  action                   ENUM('accepted','rejected','ignored','not_applicable') NULL,
  acted_at                 DATETIME    NULL,
  consecutive_reject_count TINYINT     NOT NULL DEFAULT 0,
  cooldown_choice          ENUM('7d','30d','until_manual') NULL,
  exclude_until            DATETIME    NULL,
  suppressed_until_manual  BOOLEAN     NOT NULL DEFAULT FALSE,
  conversation_snapshot    JSON        NULL COMMENT '개인정보는 담지 않는다',
  llm_model_version        VARCHAR(32) NULL,
  evidence_card_ids        JSON        NULL COMMENT '승인 근거 카드 ID 배열',
  proposed_goal            JSON        NULL COMMENT '서버 검증을 통과한 개인 목표',
  created_at               DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_cr_user_recommended (user_id, recommended_at),
  CONSTRAINT fk_cr_user  FOREIGN KEY (user_id)      REFERENCES users (id),
  CONSTRAINT fk_cr_ch    FOREIGN KEY (challenge_id) REFERENCES challenges (id),
  CONSTRAINT fk_cr_cycle FOREIGN KEY (cycle_id)     REFERENCES user_attack_cycles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='추천·거절 이력';

CREATE TABLE user_challenges (
  id                          BIGINT       NOT NULL AUTO_INCREMENT,
  user_id                     BIGINT       NOT NULL COMMENT "status='active'는 사용자당 최대 3개",
  challenge_id                BIGINT       NOT NULL,
  recommendation_id           BIGINT       NULL,
  source_prediction_id        BIGINT       NULL,
  cycle_id                    BIGINT       NULL COMMENT '레거시·주기 밖 미션만 NULL',
  status                      ENUM('active','completed','graduated','abandoned') NOT NULL DEFAULT 'active',
  start_date                  DATE         NOT NULL,
  end_date                    DATE         NOT NULL COMMENT '주기 공통 마지막 수행 가능 날짜. 포함',
  daily_target_count_snapshot TINYINT      NOT NULL,
  target_value_snapshot       DECIMAL(6,1) NULL,
  duration_days_snapshot      SMALLINT     NOT NULL COMMENT 'end_date - start_date + 1',
  completed_at                DATETIME     NULL,
  stopped_at                  DATETIME     NULL,
  stop_reason                 VARCHAR(100) NULL,
  habit_established           BOOLEAN      NULL DEFAULT NULL COMMENT '1단계는 판정 유예. NULL=미평가',
  goal_config_snapshot        JSON         NULL COMMENT '예정 기회 배열은 담지 않는다',
  completed_occurrence_count  SMALLINT     NULL COMMENT '종료 시점 인정 완료 기회 수',
  planned_occurrence_count    SMALLINT     NULL COMMENT '종료 시점 예정 기회 수. 수행률 분모',
  completion_rate             DECIMAL(5,4) NULL COMMENT '분모 0이면 NULL',
  summary_computed_at         DATETIME     NULL,
  summary_policy_version      VARCHAR(20)  NULL,
  created_at                  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at                  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_uc_user_status (user_id, status),
  KEY ix_uc_cycle (cycle_id),
  CONSTRAINT fk_uc_user  FOREIGN KEY (user_id)              REFERENCES users (id),
  CONSTRAINT fk_uc_ch    FOREIGN KEY (challenge_id)         REFERENCES challenges (id),
  CONSTRAINT fk_uc_rec   FOREIGN KEY (recommendation_id)    REFERENCES challenge_recommendations (id),
  CONSTRAINT fk_uc_pred  FOREIGN KEY (source_prediction_id) REFERENCES predictions (id),
  CONSTRAINT fk_uc_cycle FOREIGN KEY (cycle_id)             REFERENCES user_attack_cycles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='사용자 챌린지';

CREATE TABLE challenge_logs (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  user_challenge_id   BIGINT       NOT NULL,
  log_date            DATE         NOT NULL,
  occurred_at         DATETIME     NOT NULL,
  sequence_no         TINYINT      NOT NULL DEFAULT 1,
  context_slot        ENUM('lunch','dinner') NULL,
  value               DECIMAL(6,1) NULL,
  unit                VARCHAR(20)  NULL,
  result              ENUM('done','skipped') NOT NULL DEFAULT 'done',
  verification_method ENUM('manual','photo','timer','value','time','system','manual_fallback')
                        NOT NULL DEFAULT 'timer',
  verification_status ENUM('pending','pass','fail','uncertain','self_confirmed')
                        NOT NULL DEFAULT 'self_confirmed',
  evidence_url        VARCHAR(255) NULL COMMENT 'JPEG·PNG 최대 10MiB. 탈퇴 30일 후 삭제',
  verification_score  DECIMAL(4,3) NULL COMMENT 'MVP에서는 항상 NULL',
  fallback_reason     VARCHAR(100) NULL,
  reward_eligible     BOOLEAN      NOT NULL DEFAULT TRUE COMMENT '목표 초과 로그는 FALSE',
  xp_granted          SMALLINT     NOT NULL DEFAULT 0,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cl_slot (user_challenge_id, log_date, context_slot),
  KEY ix_cl_uc_date (user_challenge_id, log_date),
  CONSTRAINT fk_cl_uc FOREIGN KEY (user_challenge_id) REFERENCES user_challenges (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='수행 기록';

CREATE TABLE user_challenge_occurrences (
  id                BIGINT      NOT NULL AUTO_INCREMENT,
  user_challenge_id BIGINT      NOT NULL,
  scheduled_date    DATE        NOT NULL COMMENT 'KST 달력 날짜',
  slot_code         VARCHAR(20) NOT NULL DEFAULT '' COMMENT "lunch·dinner 등. 독립 회차는 빈 문자열. NULL은 유니크가 걸리지 않아 쓰지 않는다",
  sequence_no       TINYINT     NOT NULL DEFAULT 1 COMMENT '같은 날 독립 회차 번호',
  status            ENUM('planned','completed','skipped','missed') NOT NULL DEFAULT 'planned'
                      COMMENT 'completed만 수행률 분자. skipped·missed는 분모에만 남는다',
  completed_log_id  BIGINT      NULL COMMENT '이 기회를 인정한 수행 기록',
  completed_at      DATETIME    NULL,
  created_at        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_uco_slot (user_challenge_id, scheduled_date, slot_code, sequence_no),
  UNIQUE KEY uq_uco_log (completed_log_id),
  KEY ix_uco_uc_status (user_challenge_id, status),
  KEY ix_uco_date (scheduled_date),
  CONSTRAINT fk_uco_uc  FOREIGN KEY (user_challenge_id) REFERENCES user_challenges (id),
  CONSTRAINT fk_uco_log FOREIGN KEY (completed_log_id)  REFERENCES challenge_logs (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='예정 기회';

-- ---------------------------------------------------------------- 보상

CREATE TABLE rewards (
  id                    BIGINT       NOT NULL AUTO_INCREMENT,
  code                  VARCHAR(40)  NOT NULL,
  name                  VARCHAR(60)  NOT NULL,
  motivation_type       ENUM('collect','grow','decorate') NOT NULL,
  reward_kind           ENUM('item','badge','theme','card') NOT NULL,
  unlock_condition      VARCHAR(120) NOT NULL COMMENT '레벨 N 도달 · 챌린지 M회 누적 등',
  required_level        SMALLINT     NULL,
  linked_challenge_code VARCHAR(40)  NULL,
  is_enabled            BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_rw_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='보상 마스터';

CREATE TABLE user_rewards (
  id          BIGINT   NOT NULL AUTO_INCREMENT,
  user_id     BIGINT   NOT NULL,
  reward_id   BIGINT   NOT NULL,
  item_level  TINYINT  NOT NULL DEFAULT 1 COMMENT '아이템 성장 단계',
  acquired_at DATETIME NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ur_user_reward (user_id, reward_id) COMMENT '재요청 중복 INSERT 방지',
  CONSTRAINT fk_ur_user   FOREIGN KEY (user_id)   REFERENCES users (id),
  CONSTRAINT fk_ur_reward FOREIGN KEY (reward_id) REFERENCES rewards (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='보상 획득 이력';

SET FOREIGN_KEY_CHECKS = 1;
