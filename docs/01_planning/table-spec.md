# 당고킬러 테이블 명세서

> 원본은 구글 시트 `당고킬러_테이블명세서`입니다. 이 파일은 2026-10-01 기준 사본입니다.
> 스키마를 바꿀 때는 시트를 먼저 고치고 팀에 알린 뒤 이 파일을 다시 뽑습니다.

## 테이블 목록

| No | 테이블 | 한글명 | 담당 | API | 컬럼 수 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | users | 회원 | 배수빈 (A) | /auth /users | 21 | 레벨·경험치 컬럼 2개 추가 (9/24 결정) |
| 2 | health_records | 건강정보 기록 | 최병주 (C) | /health-records | 26 |  |
| 3 | predictions | 예측 결과 | 홍서윤 (B) | /predictions | 15 |  |
| 4 | prediction_contributions | 기여요인 | 홍서윤 (B) | /predictions | 8 | 신규 — 기여요인을 별도 테이블로 분리 (홍서윤 확인 대기) |
| 5 | monsters | 캐릭터 마스터 | 김이경 (D) | /monsters | 11 | 신규 — 도감 상태 저장이 기존 8개 안에 없었음 |
| 6 | user_monsters | 사용자 캐릭터 상태 | 김이경 (D) | /monsters | 16 | 신규 — 도감 상태 저장이 기존 8개 안에 없었음 |
| 7 | challenges | 챌린지 마스터 | 김이경 (D) | /challenges | 25 | safety_check_required 추가 (9/30 REQ-CHLG-010) |
| 8 | user_challenges | 사용자 챌린지 | 김이경 (D) | /challenges | 16 |  |
| 9 | challenge_logs | 수행 기록 | 김이경 (D) | /challenges | 17 |  |
| 10 | challenge_recommendations | 추천·거절 이력 | 김이경 (D) | /challenges | 15 |  |
| 11 | rewards | 보상 마스터 | 김이경 (D) | /rewards | 11 |  |
| 12 | user_rewards | 보상 획득 이력 | 김이경 (D) | /rewards | 6 |  |
|  | 합계 12개 테이블 · 컬럼 187개 |  |  |  |  |  |

## 테이블별 컬럼 명세

### users — 회원
담당 배수빈 (A) · 21컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT | 사용자 식별자 | 확정 |
| 2 | email | VARCHAR(255) | NN | UQ |  | 로그인 이메일 | 확정 |
| 3 | password_hash | VARCHAR(255) | NN |  |  | 해시 저장. 평문·로그 금지 (NFR-SEC-003) | 확정 |
| 4 | nickname | VARCHAR(50) | NN |  |  | 표시 이름 | 확정 |
| 5 | birth_year | SMALLINT | NULL |  |  | 출생연도. 나이는 조회 시 계산한다. 나이를 직접 저장하면 해가 바뀔 때 틀어진다 | 확정 |
| 6 | sex | ENUM('M','F') | NULL |  |  | 성별 | 확정 |
| 7 | height_cm | DECIMAL(4,1) | NULL |  |  | 키. 건강정보 입력 시 기본값으로 사용 | 확정 |
| 8 | motivation_type | ENUM('collect','grow','decorate') | NN |  | 'collect' | 보상 유형 — 수집형·성장형·꾸미기형 (REQ-USER-008) | 확정 |
| 9 | dm_diagnosed | BOOLEAN | NN |  | FALSE | 당뇨 진단 이력 (REQ-USER-007) | 확정 |
| 10 | htn_diagnosed | BOOLEAN | NN |  | FALSE | 고혈압 진단 이력 | 확정 |
| 11 | dm_medication | BOOLEAN | NN |  | FALSE | 당뇨약·인슐린 복용 여부 | 확정 |
| 12 | htn_medication | BOOLEAN | NN |  | FALSE | 혈압약 복용 여부 | 확정 |
| 13 | total_xp | INT | NN |  | 0 | 누적 경험치 (REQ-RECO-003) | 신규 — 9/24 레벨 도입 결정 |
| 14 | level | SMALLINT | NN |  | 1 | 현재 레벨. total_xp에서 파생되나 조회 편의로 함께 저장 | 신규 — 9/24 레벨 도입 결정 |
| 15 | disclaimer_agreed_at | DATETIME | NULL |  |  | 참고용 고지 동의 일시 (REQ-USER-010) | 확정 |
| 16 | login_fail_count | TINYINT | NN |  | 0 | 연속 로그인 실패 횟수 (REQ-USER-004) | 확정 |
| 17 | locked_until | DATETIME | NULL |  |  | 잠금 해제 시각. 5회 실패 시 10분 | 확정 |
| 18 | status | ENUM('active','withdrawn') | NN |  | 'active' | 탈퇴 시 비활성 (REQ-USER-009) | 확정 |
| 19 | withdrawn_at | DATETIME | NULL |  |  | 탈퇴 시각. +30일에 식별정보 삭제 | 확정 |
| 20 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |
| 21 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### health_records — 건강정보 기록
담당 최병주 (C) · 26컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | user_id | BIGINT | NN | FK |  | → users.id | 확정 |
| 3 | recorded_at | DATETIME | NN |  |  | 입력 시점. 덮어쓰지 않고 누적 (REQ-HLTH-004) | 확정 |
| 4 | input_mode | ENUM('simple','detail') | NN |  | 'simple' | 간편 / 정밀 | 확정 |
| 5 | weight_kg | DECIMAL(4,1) | NULL |  |  |  | 확정 |
| 6 | waist_cm | DECIMAL(4,1) | NULL |  |  | 허리둘레 | 확정 |
| 7 | bmi | DECIMAL(4,1) | NULL |  |  | 키·몸무게에서 계산해 저장 | 확정 |
| 8 | smoking_current | BOOLEAN | NULL |  |  | 현재 흡연 여부 | 확정 |
| 9 | alcohol_frequency | TINYINT | NULL |  |  | 1년간 음주 빈도 코드 | 확정 |
| 10 | alcohol_amount | TINYINT | NULL |  |  | 1회 음주량 코드 | 확정 |
| 11 | walking_days | TINYINT | NULL |  |  | 주당 걷기 일수 0~7 | 확정 |
| 12 | walking_minutes | SMALLINT | NULL |  |  | 1회 걷기 시간(분) | 확정 |
| 13 | strength_days | TINYINT | NULL |  |  | 주당 근력운동 일수 0~7 | 확정 |
| 14 | sitting_minutes | SMALLINT | NULL |  |  | 하루 앉아 있는 시간(분) | 확정 |
| 15 | family_history_dm | BOOLEAN | NULL |  |  | 당뇨 가족력 | 확정 |
| 16 | family_history_htn | BOOLEAN | NULL |  |  | 고혈압 가족력 | 확정 |
| 17 | dining_out_freq | TINYINT | NULL |  |  | 외식 빈도 1~7 (1 거의 매일 2회+ ~ 7 거의 안 함). 소디 위협도 산출 (REQ-CHLG-009) | 신규 — 9/25 간편모드 10문항 |
| 18 | sbp | SMALLINT | NULL |  |  | 수축기 혈압 — 정밀 모드 | 확정 |
| 19 | dbp | SMALLINT | NULL |  |  | 이완기 혈압 — 정밀 모드 | 확정 |
| 20 | fasting_glucose | SMALLINT | NULL |  |  | 공복혈당 — 정밀 모드. 스파이크 위협도 산출에 사용 | 확정 |
| 21 | hba1c | DECIMAL(3,1) | NULL |  |  | 당화혈색소 — 정밀 모드 | 확정 |
| 22 | triglyceride | SMALLINT | NULL |  |  | 중성지방 — 대사증후군 판정 | 확정 |
| 23 | hdl | SMALLINT | NULL |  |  | HDL 콜레스테롤 — 대사증후군 판정 | 확정 |
| 24 | total_cholesterol | SMALLINT | NULL |  |  | 총콜레스테롤 | 확정 |
| 25 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |
| 26 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### predictions — 예측 결과
담당 홍서윤 (B) · 15컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | user_id | BIGINT | NN | FK |  | → users.id | 확정 |
| 3 | health_record_id | BIGINT | NN | FK |  | → health_records.id · 어떤 입력으로 예측했는지 | 확정 |
| 4 | job_id | VARCHAR(64) | NN | UQ |  | 비동기 작업 식별자 (REQ-PRED-002) | 확정 |
| 5 | status | ENUM('pending','done','failed') | NN |  | 'pending' | 추론 상태 (NFR-REL-001) | 확정 |
| 6 | dm_probability | DECIMAL(5,4) | NULL |  |  | 당뇨 위험 확률 0~1 | 확정 |
| 7 | dm_grade | ENUM('low','caution','high') | NULL |  |  | 3단계 등급 (REQ-PRED-004) | 확정 |
| 8 | htn_probability | DECIMAL(5,4) | NULL |  |  | 고혈압 위험 확률 | 확정 |
| 9 | htn_grade | ENUM('low','caution','high') | NULL |  |  |  | 확정 |
| 10 | metabolic_count | TINYINT | NULL |  |  | 대사증후군 해당 지표 수 0~5 (REQ-PRED-009) | 확정 |
| 11 | model_version | VARCHAR(32) | NN |  |  | 모델 버전 고정 (NFR-MODL-002) | 확정 |
| 12 | input_snapshot | JSON | NULL |  |  | 예측 당시 모델 입력 스냅샷. 전처리 전 canonical 값·단위와 결측 여부를 보존하며 model_version에 연결된 전처리·모델 아티팩트로 과거 결과를 검증한다. 혈압·혈당·진단·약물은 모델 X에서 제외 (REQ-PRED-003) | 확정 — 홍서윤 9/30 |
| 13 | predicted_at | DATETIME | NULL |  |  | 추론 완료 시각 | 확정 |
| 14 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP | 요청 접수 시각 | 확정 |
| 15 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### prediction_contributions — 기여요인
담당 홍서윤 (B) · 8컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | prediction_id | BIGINT | NN | FK |  | → predictions.id | 확정 |
| 3 | disease | ENUM('diabetes','hypertension') | NN |  |  | 기여도를 산출한 질환 모델: diabetes 또는 hypertension. 미진단 질환만 개인 예측·SHAP을 생성하며 같은 factor도 질환별 행으로 분리한다 | 확정 — 홍서윤 9/30 |
| 4 | factor_key | VARCHAR(50) | NN |  |  | 공통 요인 코드. 값 목록은 Feature Dictionary v0 · 13개 | 확정 — 9/28 Mapping v1 |
| 5 | contribution | DECIMAL(8,5) | NN |  |  | 정규화 전 signed grouped SHAP(확률 단위). 같은 factor의 원시/one-hot SHAP을 부호 유지 합산하고 DECIMAL(8,5)로 저장. 0 포함 지원 factor 전량 저장; 위협도 정규화 상수는 model_version 메타데이터에 고정 | 확정 — 홍서윤 9/30 |
| 6 | direction | ENUM('increase','decrease') | NN |  |  | 저장 contribution > 0이면 increase, <= 0이면 decrease. 0은 ENUM 제약에 따른 decrease이며 보호 효과를 뜻하지 않는다. 0·음수의 위협도는 0 | 확정 — 홍서윤 9/30 |
| 7 | rank | TINYINT | NN |  |  | 질환별 abs(저장 contribution) 내림차순, 동률은 factor_key 오름차순의 1기반 순위. 0 포함 지원 factor 전량 저장하며 Top3는 화면 표시 범위만 뜻한다 (REQ-PRED-005) | 확정 — 홍서윤 9/30 |
| 8 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |

### monsters — 캐릭터 마스터
담당 김이경 (D) · 11컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | code | VARCHAR(20) | NN | UQ |  | spike / alde / cotinine / viscera / sodi | 확정 |
| 3 | no | TINYINT | NN | UQ |  | 도감 번호 1~5 | 확정 |
| 4 | name | VARCHAR(30) | NN |  |  | 스파이크 · 알데 · 코티니 · 비세라 · 소디 | 확정 |
| 5 | title | VARCHAR(60) | NULL |  |  | 식후 한 시간의 폭군 등 | 확정 |
| 6 | factor_keys | JSON | NN |  |  | 연결된 factor_key 배열 (REQ-CHLG-007) | 확정 — 9/28 Mapping v1 |
| 7 | disease_scope | ENUM('common','diabetes','hypertension') | NN |  | 'common' | 스파이크는 diabetes, 소디는 hypertension, 나머지 셋은 common | 확정 |
| 8 | default_impact_source | ENUM('contribution','measured') | NN |  | 'contribution' | 이 캐릭터의 기본 위협도 산출 방식. 스파이크는 measured (REQ-PRED-010). 소디는 모델 적합성 확인 후 확정 | 변경 — 9/28 용어 치환 |
| 9 | is_enabled | BOOLEAN | NN |  | TRUE |  | 확정 |
| 10 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |
| 11 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### user_monsters — 사용자 캐릭터 상태
담당 김이경 (D) · 16컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | user_id | BIGINT | NN | FK |  | → users.id | 확정 |
| 3 | monster_id | BIGINT | NN | FK |  | → monsters.id · (user_id, monster_id) 유니크 | 확정 |
| 4 | impact_score | TINYINT | NULL |  |  | 위협도 0~100. 그 요인이 내 위험도를 얼마나 밀어올렸는지. NULL이면 미측정 (스파이크 정밀모드 미입력) | 변경 — 9/28 용어 치환 |
| 5 | state | ENUM('rage','caution','stable','not_contributing','resolved','sealed','unmeasured') | NN |  | 'unmeasured' | 분노·경계·안정·현재 위험 기여 없음·요인 해소됨·봉인·미측정. 공략 대상은 rage/caution/stable만. score=0이면 resolved_at 및 직전 state 기준으로 resolved/not_contributing 분기 | 변경 — 9/29 SHAP 음수·해소 상태 확정 |
| 6 | sealed_at | DATETIME | NULL |  |  | 봉인 시각. 최근 28일 중 해당 factor 챌린지 성공일 20일 이상 + 위협도 40 미만 달성 시 기록 | 변경 — 9/29 봉인 기준 최신화 |
| 7 | resolved_at | DATETIME | NULL |  |  | 위협이었던 요인이 처음 score=0이 된 시각. 한 번 기록되면 이후 unmeasured를 거쳐도 유지하며 지우지 않는다. 한 번도 위협이 아니었던 요인은 NULL | 신규 — 9/29 해소 이력 보존 |
| 8 | reawakened_at | DATETIME | NULL |  |  | 재각성 시각. 기록 4주 단절 | 확정 |
| 9 | seal_count | SMALLINT | NN |  | 0 | 누적 봉인 횟수. 도감 기록용 | 확정 |
| 10 | impact_source | ENUM('contribution','measured','global') | NN |  | 'contribution' | 이 사용자의 위협도를 산출한 실제 방식. contribution=미진단자 SHAP · measured=실측(스파이크) · global=진단자 전역중요도 | 신규 — 9/28 진단자 경로 |
| 11 | last_prediction_id | BIGINT | NULL | FK |  | → predictions.id · contribution 방식일 때 근거 예측. 진단자·실측은 NULL | 확정 |
| 12 | last_health_record_id | BIGINT | NULL | FK |  | → health_records.id · measured·global 방식일 때 근거 입력. contribution은 NULL | 신규 — 9/28 진단자 경로 |
| 13 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |
| 14 | weekly_progress | SMALLINT | NN |  | 0 | 이번 주 누적 공략 점수. 챌린지 수행 시 즉시 증가하되 DB 저장값은 최대 100으로 제한한다. 위협도는 건드리지 않는다 (REQ-PRED-011). 화면 목표는 100 고정이다. 100 미달에 불이익은 없고 게임 진행 표시용이다. | 확정 — 10/1 PR #8 주간 공략 점수 100 상한 반영 |
| 15 | progress_week_start | DATE | NULL |  |  | 공략 점수 누적 기준 주 시작일. 해당 주 월요일 날짜를 저장한다. 월요일 00:00 KST에 weekly_progress를 0으로 초기화한다. C의 대시보드 week_start와 같은 달력 주간 기준 | 확정 — 9/29 월요일 기준 |
| 16 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### challenges — 챌린지 마스터
담당 김이경 (D) · 25컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | code | VARCHAR(40) | NN | UQ |  | 고유 코드 | 확정 |
| 3 | title | VARCHAR(80) | NN |  |  | 식후 10분 걷기 등 | 확정 |
| 4 | description | VARCHAR(255) | NULL |  |  | 수행 설명 | 확정 |
| 5 | category | ENUM('activity','diet','smoking','alcohol','body','sleep') | NN |  |  | sleep은 모델 요인이 아닌 보너스 챌린지용 | 변경 — 9/25 김이경 요청 |
| 6 | factor_key | VARCHAR(50) | NULL |  |  | 연결 요인. 추천과 공략 점수 반영의 기준. NULL이면 모델과 무관한 보너스 챌린지 — XP·보상만 주고 공략 점수는 쌓이지 않음 | 변경 — 9/25 김이경 요청 |
| 7 | goal_type | ENUM('boolean','count','duration','quantity') | NN |  |  |  | 확정 |
| 8 | target_value | DECIMAL(6,1) | NULL |  |  | 1회 목표값 | 확정 |
| 9 | unit | VARCHAR(20) | NULL |  |  | 분 · 회 · 잔 등 | 확정 |
| 10 | daily_target_count | TINYINT | NN |  | 1 | 하루 목표 수행 횟수 (REQ-CHLG-003) | 확정 |
| 11 | duration_days | SMALLINT | NN |  | 7 | 개별 챌린지 기간. 7일 단위로 유지·교체·난이도 조정 (Mapping v0). 4주는 챌린지 기간이 아니라 재입력·위협도 갱신·봉인 판단의 관리 주기 | 변경 — 9/28 김이경 Mapping v0 |
| 12 | verification_type | ENUM('manual','photo','timer','value','time','system') | NN |  | 'timer' | 인증 수단 1개. Mapping v0의 PHOTO·TIMER·VALUE·TIME·SYSTEM에 대응 (REQ-CHLG-008 개정 필요) | 변경 — 9/28 김이경 Mapping v0 |
| 13 | difficulty | ENUM('easy','normal','challenge') | NN |  | 'easy' | 추천 우선순위 조정용 | 신규 — 9/28 김이경 Mapping v0 |
| 14 | relation_type | ENUM('direct','supporting','general') | NN |  | 'supporting' | direct=서비스 입력값을 직접 바꿈 · supporting=관련 행동 · general=모델 비연계 | 신규 — 9/28 김이경 Mapping v0 |
| 15 | exclude_condition | VARCHAR(200) | NULL |  |  | 추천 제외 조건 설명. 시스템 판정이 가능한 것만 코드로 구현 | 신규 — 9/28 김이경 Mapping v0 |
| 16 | context_label | VARCHAR(40) | NULL |  |  | 화면 표시용 맥락 문구. 기상 후 · 음주 이벤트 · 좌식 중 등 | 신규 — 9/28 김이경 Mapping v0 |
| 17 | manual_fallback_allowed | BOOLEAN | NN |  | TRUE |  | 확정 |
| 18 | context_type | ENUM('none','meal','event') | NN |  | 'none' | 시각이 아닌 맥락. event는 음주·흡연처럼 기회가 생긴 날에만 수행 가능 | 변경 — 9/28 김이경 Mapping v0 |
| 19 | context_slots | JSON | NULL |  |  | ['lunch','dinner'] | 확정 |
| 20 | reward_xp | SMALLINT | NN |  | 0 | 1회 수행당 지급 경험치 | 신규 — 9/24 레벨 도입 결정 |
| 21 | progress_value | SMALLINT | NN |  | 10 | 인정된 수행 1회당 쌓이는 공략 점수. MVP는 전 챌린지 동일 값. factor_key가 NULL이면 반드시 0 (마스터 데이터 규칙, REQ-PRED-011) | 변경 — 9/28 용어 치환 |
| 22 | is_enabled | BOOLEAN | NN |  | TRUE | 운영 중인 정의인지 | 확정 |
| 23 | safety_check_required | BOOLEAN | NN |  | FALSE | 운동 전 안전 확인이 필요한 챌린지 여부. TRUE이면 챌린지 시작 요청에서 safety_confirmed=true를 서버가 검증한다. safety_confirmed 응답값 자체는 저장하지 않는다. category='activity' 전체가 아니라 마스터 데이터에서 필요한 챌린지만 TRUE로 지정한다. (REQ-CHLG-010) | 신규 — 9/30 REQ-CHLG-010 안전확인 판정 |
| 24 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |
| 25 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### user_challenges — 사용자 챌린지
담당 김이경 (D) · 16컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | user_id | BIGINT | NN | FK |  | → users.id · status='active'는 사용자당 최대 3개 (REQ-CHLG-002) | 확정 |
| 3 | challenge_id | BIGINT | NN | FK |  | → challenges.id | 확정 |
| 4 | recommendation_id | BIGINT | NULL | FK |  | → challenge_recommendations.id · 어느 카드에서 시작했는지 | 확정 |
| 5 | source_prediction_id | BIGINT | NULL | FK |  | → predictions.id · 미진단 질환의 개인 기여도 기반 추천이면 근거 prediction_id. 진단 질환의 전역 중요도 기반 추천·보너스는 NULL. 한 질환만 진단받은 사용자는 다른 미진단 질환 추천의 prediction_id를 가질 수 있다 | 확정 — 홍서윤 9/30 |
| 6 | status | ENUM('active','completed','abandoned') | NN |  | 'active' |  | 확정 |
| 7 | start_date | DATE | NN |  |  |  | 확정 |
| 8 | end_date | DATE | NN |  |  |  | 확정 |
| 9 | daily_target_count_snapshot | TINYINT | NN |  |  | 시작 당시 목표 횟수 보존 | 확정 |
| 10 | target_value_snapshot | DECIMAL(6,1) | NULL |  |  | 마스터가 바뀌어도 과거 기록 보존 | 확정 |
| 11 | duration_days_snapshot | SMALLINT | NN |  |  |  | 확정 |
| 12 | completed_at | DATETIME | NULL |  |  |  | 확정 |
| 13 | stopped_at | DATETIME | NULL |  |  |  | 확정 |
| 14 | stop_reason | VARCHAR(100) | NULL |  |  | 중단 사유 (REQ-CHLG-005) | 확정 |
| 15 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |
| 16 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### challenge_logs — 수행 기록
담당 김이경 (D) · 17컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | user_challenge_id | BIGINT | NN | FK |  | → user_challenges.id | 확정 |
| 3 | log_date | DATE | NN |  |  | 수행 날짜 | 확정 |
| 4 | occurred_at | DATETIME | NN |  |  | 수행 시각 | 확정 |
| 5 | sequence_no | TINYINT | NN |  | 1 | 그날 몇 번째 수행인지 | 확정 |
| 6 | context_slot | ENUM('lunch','dinner') | NULL |  |  | 식사 맥락. (user_challenge_id, log_date, context_slot) 유니크로 같은 슬롯 중복 차단. 횟수형은 NULL이라 제약을 받지 않음 | 확정 |
| 7 | value | DECIMAL(6,1) | NULL |  |  | 실제 수행값 | 확정 |
| 8 | unit | VARCHAR(20) | NULL |  |  |  | 확정 |
| 9 | result | ENUM('done','skipped') | NN |  | 'done' |  | 확정 |
| 10 | verification_method | ENUM('manual','photo','timer','value','time','system','manual_fallback') | NN |  | 'timer' | 챌린지의 verification_type과 일치. photo는 AI 판정 없이 업로드 여부만 확인 | 변경 — 9/28 김이경 Mapping v0 |
| 11 | verification_status | ENUM('pending','pass','fail','uncertain','self_confirmed') | NN |  | 'self_confirmed' |  | 확정 |
| 12 | evidence_url | VARCHAR(255) | NULL |  |  | 증빙 사진 참조값. photo 인증이면 필수. C의 HLTH-03이 반환하는 비공개 참조값을 저장한다 — 공개 정적 URL이 아니다. JPEG·PNG, 최대 10MiB. 탈퇴 30일 후 삭제 (NFR-SEC-005) | 확정 — 9/28 최병주 HLTH-03 |
| 13 | verification_score | DECIMAL(4,3) | NULL |  |  | 2차 범위 — 사진 AI 판별 confidence. MVP에서는 항상 NULL | 확정 |
| 14 | fallback_reason | VARCHAR(100) | NULL |  |  |  | 확정 |
| 15 | reward_eligible | BOOLEAN | NN |  | TRUE | 목표 초과 로그는 FALSE (REQ-CHLG-003) | 확정 |
| 16 | xp_granted | SMALLINT | NN |  | 0 | 실제 지급된 경험치. reward_eligible=FALSE면 0 | 신규 — 9/24 레벨 도입 결정 |
| 17 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |

### challenge_recommendations — 추천·거절 이력
담당 김이경 (D) · 15컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | user_id | BIGINT | NN | FK |  | → users.id | 확정 |
| 3 | challenge_id | BIGINT | NN | FK |  | → challenges.id | 확정 |
| 4 | source_type | ENUM('prediction_personal','diagnosis_global') | NN |  |  | 미진단자 개인 기여도 / 진단자 전역 중요도 (REQ-CHLG-001) | 확정 |
| 5 | factor_key | VARCHAR(50) | NN |  |  | MVP 추천 근거 요인. factor 기반 추천만 생성하므로 NOT NULL. challenges.factor_key=NULL인 일반/보너스 챌린지는 현재 factor 기반 추천 흐름에서 제외한다. | 확정 — 9/29 D 추천 규칙 정합성 수정 |
| 6 | factor_score | DECIMAL(8,5) | NULL |  |  | 추천 점수 | 확정 |
| 7 | rank | TINYINT | NN |  |  | 카드 순위 1~3 | 확정 |
| 8 | recommended_at | DATETIME | NN |  |  |  | 확정 |
| 9 | action | ENUM('accepted','rejected','ignored','not_applicable') | NULL |  |  | not_applicable은 '이건 저한테 해당 없어요'. 연속 거절 횟수에 포함하지 않고 바로 숨긴다 | 변경 — 9/28 김이경 제외조건 합의 |
| 10 | acted_at | DATETIME | NULL |  |  |  | 확정 |
| 11 | consecutive_reject_count | TINYINT | NN |  | 0 | 동일 챌린지 연속 거절 횟수. action='not_applicable'은 세지 않는다 | 변경 — 9/28 김이경 제외조건 합의 |
| 12 | cooldown_choice | ENUM('7d','30d','until_manual') | NULL |  |  | 3회 거절 시 사용자 선택 (REQ-CHLG-006) | 확정 |
| 13 | exclude_until | DATETIME | NULL |  |  | 기간형 쿨다운 종료 | 확정 |
| 14 | suppressed_until_manual | BOOLEAN | NN |  | FALSE | 직접 해제할 때까지 숨김. 3회 연속 거절 또는 not_applicable 선택 시 TRUE | 변경 — 9/28 김이경 제외조건 합의 |
| 15 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |

### rewards — 보상 마스터
담당 김이경 (D) · 11컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | code | VARCHAR(40) | NN | UQ |  | gluco_blade 등 | 확정 |
| 3 | name | VARCHAR(60) | NN |  |  | 글루코 블레이드 등 | 확정 |
| 4 | motivation_type | ENUM('collect','grow','decorate') | NN |  |  | 어느 보상 유형에 주는지 | 확정 |
| 5 | reward_kind | ENUM('item','badge','theme','card') | NN |  |  |  | 확정 |
| 6 | unlock_condition | VARCHAR(120) | NN |  |  | 레벨 N 도달 · 챌린지 M회 누적 등. 단계별 누적 0·7·28·84회 | 확정 — 9/28 Mapping v1 · 기획서 4.5 |
| 7 | required_level | SMALLINT | NULL |  |  | 레벨업 보상인 경우 | 신규 — 9/24 레벨 도입 결정 |
| 8 | linked_challenge_code | VARCHAR(40) | NULL |  |  | 연결 챌린지. 아이템 성장 계산에 사용 | 확정 |
| 9 | is_enabled | BOOLEAN | NN |  | TRUE |  | 확정 |
| 10 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |
| 11 | updated_at | DATETIME | NN |  | ON UPDATE |  | 확정 |

### user_rewards — 보상 획득 이력
담당 김이경 (D) · 6컬럼

| No | 컬럼명 | 타입 | NULL | 키 | 기본값 | 설명 | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | BIGINT | NN | PK | AUTO_INCREMENT |  | 확정 |
| 2 | user_id | BIGINT | NN | FK |  | → users.id | 확정 |
| 3 | reward_id | BIGINT | NN | FK |  | → rewards.id · (user_id, reward_id) 유니크 — 재요청 중복 INSERT 방지 | 확정 |
| 4 | item_level | TINYINT | NN |  | 1 | 아이템 성장 단계. challenge_logs 누적에서 계산 | 확정 |
| 5 | acquired_at | DATETIME | NN |  |  |  | 확정 |
| 6 | created_at | DATETIME | NN |  | CURRENT_TIMESTAMP |  | 확정 |

## 관계 (FK)

| No | FROM | TO | 관계 | 설명 | 합의 필요 |
| --- | --- | --- | --- | --- | --- |
| 1 | health_records.user_id | users.id | N : 1 | 사용자 한 명이 기록 여러 개 | 최병주 |
| 2 | predictions.user_id | users.id | N : 1 |  | 홍서윤 |
| 3 | predictions.health_record_id | health_records.id | N : 1 | 어떤 입력으로 예측했는지 | 홍서윤 ↔ 최병주 |
| 4 | prediction_contributions.prediction_id | predictions.id | N : 1 | 예측 1건당 질환 2종 × 요인 N개 | 홍서윤 |
| 5 | user_monsters.user_id | users.id | N : 1 | (user_id, monster_id) 유니크 | 김이경 |
| 6 | user_monsters.monster_id | monsters.id | N : 1 |  | 김이경 |
| 7 | user_monsters.last_prediction_id | predictions.id | N : 1 | NULL 허용 — 진단자·실측 | 김이경 ↔ 홍서윤 |
| 8 | user_monsters.last_health_record_id | health_records.id | N : 1 | NULL 허용 — 미진단자 SHAP | 김이경 ↔ 최병주 |
| 9 | user_challenges.user_id | users.id | N : 1 | active는 최대 3개 | 김이경 |
| 10 | user_challenges.challenge_id | challenges.id | N : 1 |  | 김이경 |
| 11 | user_challenges.recommendation_id | challenge_recommendations.id | N : 1 | NULL 허용 | 김이경 |
| 12 | user_challenges.source_prediction_id | predictions.id | N : 1 | NULL 허용 — 진단자 | 김이경 ↔ 홍서윤 |
| 13 | challenge_logs.user_challenge_id | user_challenges.id | N : 1 | 하루 여러 건 가능 | 김이경 |
| 14 | challenge_recommendations.user_id | users.id | N : 1 |  | 김이경 |
| 15 | challenge_recommendations.challenge_id | challenges.id | N : 1 |  | 김이경 |
| 16 | user_rewards.user_id | users.id | N : 1 |  | 김이경 |
| 17 | user_rewards.reward_id | rewards.id | N : 1 |  | 김이경 |

## 규칙과 범례

| ■ 네이밍 규칙 — 그리기 전에 고정 |  |
| --- | --- |
| 테이블명 | 복수형 snake_case. users · health_records · challenge_logs |
| PK | 전 테이블 id · BIGINT · AUTO_INCREMENT |
| FK | {단수형}_id. user_id · challenge_id · prediction_id |
| 공통 컬럼 | created_at · updated_at 전 테이블 필수 |
| 삭제 | soft delete. 탈퇴 데이터 30일 보관 때문에 물리 삭제하지 않음 |
| 시각 | UTC DATETIME으로 저장. 화면에 보일 때만 KST 변환 |
| 불리언 | BOOLEAN. is_ 접두사는 마스터 테이블의 is_enabled에만 사용 |
| 금액·비율 | 확률은 DECIMAL(5,4) 0~1로 저장. 화면에서 %로 변환 |
| ENUM · 정수 타입 | 명세서에 ENUM으로 적은 컬럼은 Tortoise가 VARCHAR로 만들고 값 검증은 애플리케이션에서 한다. TINYINT는 SMALLINT로 생성된다. 시트는 허용되는 값을 적는 문서이고, 실제 DDL은 ERD.sql을 본다 |
| ■ 이 파일 보는 법 |  |
| 노란 칸 | 아직 확정되지 않았거나 담당자 확인이 필요한 부분입니다. 여기만 봐주세요 |
| 상태 · 확정 | 요구사항 정의서 v5에서 도출된 것으로 그대로 가면 됩니다 |
| 상태 · 확인 대기 | 담당자 답변이 있어야 확정됩니다 |
| 상태 · 검토 필요 | 제가 임의로 정한 것이라 의견이 필요합니다 |
| 상태 · 신규 | 9월 24일 회의에서 새로 결정된 것입니다 |
| ■ 채워주실 것 — 자기 테이블만 보시면 됩니다 |  |
| 배수빈 (A) | users |
| 홍서윤 (B) | predictions · prediction_contributions |
| 최병주 (C) | health_records |
| 김이경 (D) | monsters · user_monsters · challenges · user_challenges · challenge_logs · challenge_recommendations · rewards · user_rewards |
| 보는 방법 | '테이블 명세' 시트에서 담당 열로 필터를 거시면 본인 것만 나옵니다 |
| 고칠 것 | 빠진 컬럼 추가 · 타입 수정 · 노란 칸 확정. 컬럼을 지우실 때는 이유를 상태 칸에 적어주세요 |
| ■ 아직 정해지지 않은 것 |  |
| factor_key 값 목록 | 김이경 · 9월 25일. 타입은 VARCHAR(50)이라 구조에는 영향 없음 |
| 기여요인 저장 구조 | 홍서윤 확인 대기. prediction_contributions 전체 |
| 스파이크 위협도 산출 | 홍서윤 확인 대기. monsters.default_impact_source |
| 레벨별 필요 경험치 | 테이블로 만들지 않고 코드 상수로 둡니다. levels 테이블을 만들면 13개가 되고 ERD를 다시 그려야 하는데, 레벨 30개짜리 상수 배열이면 밸런스 조정 시 숫자만 바꾸면 됩니다 |
| XP 지급량 · 공략 점수 | challenges.reward_xp와 progress_value의 실제 값입니다. 컬럼과 타입은 정해져 있어 구조에는 영향이 없고, 4주차에 챌린지 목록을 채울 때 같이 정합니다 (김이경) |
| XP 갱신 주체 | users는 A만 쓰므로, D는 A가 제공하는 내부 함수로 지급을 요청합니다. 레벨 재계산과 레벨업 판정은 A에서 한 곳으로 모읍니다 |
| 리프레시 토큰 | Redis에 저장하기로 하여 테이블을 만들지 않았습니다. 다른 의견 있으면 알려주세요 |
| ■ 예시 — 이렇게 채워주시면 됩니다 |  |
| 컬럼명 | sleep_minutes |
| 타입 | SMALLINT |
| NULL | NULL |
| 키 | (비움) |
| 기본값 | (비움) |
| 설명 | 하루 수면 시간(분). 간편 모드 10번째 항목으로 추가 요청 |
| 상태 | 추가 요청 — 최병주 |
| AH_06_02 · 당고킬러 · 테이블 명세서 v2 · 2026.09.25 · 작성 배수빈 |  |
