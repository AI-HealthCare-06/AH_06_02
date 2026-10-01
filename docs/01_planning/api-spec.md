# 당고킬러 API 명세서

> 원본은 구글 시트 `당고킬러_API 명세서`입니다. 이 파일은 2026-10-01 기준 사본입니다.
> 계약을 바꿀 때는 시트를 먼저 고치고 팀에 알린 뒤 이 파일을 다시 뽑습니다.

## 공통 인증 · 응답 규칙

| 구분 | 항목 | 내용 |
| --- | --- | --- |
| 인증 | 방식 | JWT Bearer 토큰. 헤더 Authorization: Bearer {access_token} |
| 인증 | 토큰 수명 | Access 30분 / Refresh 14일. Access 만료 시 POST /api/v1/auth/refresh로 재발급 |
| 인증 | 인증 불필요 엔드포인트 | 회원가입 · 로그인 · 토큰 재발급 · 이메일 중복 확인 · 헬스체크. 그 외는 전부 인증 필요 |
| 인증 | 본인 데이터 원칙 | 개인 데이터 엔드포인트는 URL에 user_id를 받지 않는다. 항상 토큰에서 꺼낸 user_id를 쓴다 (NFR-SEC-002) |
| 인증 | 401 vs 403 | 401 = 토큰이 없거나 만료됨 · 남의 리소스를 가리키는 요청은 403이 아니라 404로 응답한다. 403을 주면 그 ID가 존재한다는 사실이 드러나 건강 데이터가 샌다 |
| 응답 | 성공 형식 | { "success": true, "data": { ... } } |
| 응답 | 실패 형식 | { "success": false, "error": { "code": "CHLG_LIMIT_EXCEEDED", "message": "동시 진행 챌린지는 최대 3개입니다." } } |
| 응답 | 목록 형식 | { "success": true, "data": { "items": [...], "total": 120, "page": 1, "size": 20 } } |
| 응답 | HTTP 상태 코드 | 200 조회·수정 · 201 생성 · 400 잘못된 요청 · 401 인증 · 403 인가 · 404 없음 · 409 충돌(중복) · 422 검증 실패 · 500 서버 |
| 응답 | message 문구 | 사용자에게 그대로 보여줄 수 있는 한국어 문장으로 쓴다. 내부 예외 메시지를 그대로 내보내지 않는다 |
| 에러 코드 | 형식 | {도메인}_{사유} 대문자 스네이크. 도메인은 AUTH · USER · HLTH · PRED · CHLG · RWRD · MNSTR |
| 에러 코드 | 공통 코드 | VALIDATION_ERROR · UNAUTHORIZED · FORBIDDEN · NOT_FOUND · INTERNAL_ERROR |
| 에러 코드 | 예시 | AUTH_EMAIL_DUPLICATED · CHLG_LIMIT_EXCEEDED · PRED_INPUT_INSUFFICIENT |
| 에러 코드 | 전체 목록 | 「에러 코드」 탭 참고 |
| 명명 | URL | 소문자 · 하이픈 구분 · 리소스는 복수형. 예: /api/v1/health-records |
| 명명 | 버전 | 모든 경로에 /api/v1 접두사 |
| 명명 | JSON 키 | snake_case. DB 컬럼명과 같게 맞춰서 변환 실수를 줄인다 |
| 명명 | 날짜·시간 | ISO 8601 UTC. 2026-09-28T11:20:00Z · 날짜만 필요하면 2026-09-28 |
| 공통 | 타임존 | 저장은 UTC. KST 변환은 프론트에서 한다 |
| 공통 | 페이징 | ?page=1&size=20 · size 기본 20, 최대 100 |
| 공통 | 정렬 | ?sort=created_at:desc 형식 |
| 공통 | soft delete | status가 withdrawn이거나 삭제 표시된 행은 조회 결과에서 제외한다 |
| 공통 | request_id | 모든 응답 헤더에 X-Request-Id를 넣는다. 로그 추적용 |
| 금지 | 비밀번호 | 평문 저장·로그 출력 금지. bcrypt 해시만 저장 (NFR-SEC-003) |
| 금지 | 비밀정보 | SECRET_KEY · API 키는 .env로만. 저장소에는 .env.example만 올린다 |

## 에러 코드 · 27개

| 도메인 | 에러 코드 | HTTP | 의미 | 쓰는 곳 |
| --- | --- | --- | --- | --- |
| 공통 | VALIDATION_ERROR | 400 | 요청 값이 형식·범위를 벗어남 | 전원 |
| 공통 | UNAUTHORIZED | 401 | 토큰이 없거나 만료됨 | 전원 |
| 공통 | FORBIDDEN | 403 | 토큰은 유효하지만 남의 리소스 | 전원 |
| 공통 | NOT_FOUND | 404 | 대상 리소스가 없음 | 전원 |
| 공통 | INTERNAL_ERROR | 500 | 서버 내부 오류 | 전원 |
| AUTH | AUTH_EMAIL_DUPLICATED | 409 | 이미 가입된 이메일 | A · AUTH-02 |
| AUTH | AUTH_WEAK_PASSWORD | 422 | 비밀번호 규칙 미달 | A · AUTH-02 · USER-04 |
| AUTH | AUTH_INVALID_CREDENTIALS | 401 | 이메일 또는 비밀번호 불일치 | A · AUTH-03 · USER-04 · USER-05 |
| AUTH | AUTH_ACCOUNT_LOCKED | 403 | 로그인 5회 연속 실패로 10분 잠금 | A · AUTH-03 |
| AUTH | AUTH_TOKEN_EXPIRED | 401 | Refresh 토큰 만료 | A · AUTH-04 |
| AUTH | AUTH_TOKEN_INVALID | 401 | Refresh 토큰이 위조됐거나 폐기됨 | A · AUTH-04 |
| HLTH | HLTH_PROFILE_INCOMPLETE | 400 | birth_year · sex · height_cm 누락 | C · HLTH-01 |
| HLTH | HLTH_VALUE_OUT_OF_RANGE | 400 | 입력값이 허용 범위를 벗어남 | C · HLTH-01 |
| HLTH | HLTH_RECORD_NOT_FOUND | 404 | 해당 health_record가 없음 | B · PRED-01 (초안) |
| PRED | PRED_ALL_DIAGNOSED | 400 | 두 질환 모두 진단이라 예측 대상 없음 | B · PRED-01 (초안) |
| PRED | PRED_INPUT_INSUFFICIENT | 400 | 모델 입력 항목이 모자람 (REQ-PRED-008) | B (초안) |
| PRED | PRED_NOT_FOUND | 404 | 완료된 예측이 없음 | B · D · CHLG-01 |
| CHLG | CHLG_LIMIT_EXCEEDED | 409 | 동시 진행 챌린지 3개 초과 | D · CHLG-05 |
| CHLG | CHLG_ALREADY_ACTIVE | 409 | 이미 진행 중인 같은 챌린지 | D · CHLG-05 |
| CHLG | CHLG_SAFETY_CONFIRMATION_REQUIRED | 400 | 운동형 챌린지인데 safety_confirmed 누락 (REQ-CHLG-010) | D · CHLG-05 |
| CHLG | CHLG_NOT_ACTIVE | 409 | 진행 중이 아닌 챌린지에 기록·중단 시도 | C · HLTH-03 · D · CHLG-07 · CHLG-09 |
| CHLG | CHLG_NOT_FOUND | 404 | 해당 user_challenge 없음 | D · CHLG-08 · CHLG-09 |
| CHLG | CHLG_LOG_DUPLICATED | 409 | 같은 날 같은 슬롯에 중복 기록 | D · CHLG-07 |
| CHLG | CHLG_VERIFICATION_FAILED | 422 | 인증 방식에 맞지 않는 값 | D · CHLG-07 |
| CHLG | CHLG_RECOMMENDATION_NOT_FOUND | 404 | 해당 추천 카드 없음 | D · CHLG-03 · 04 · 05 |
| CHLG | CHLG_RECOMMENDATION_UNAVAILABLE | 409 | 추천을 만들 근거가 없음 | D · CHLG-01 |
| CHLG | CHLG_INVALID_COOLDOWN | 400 | 쿨다운 값이 7 · 30 · manual이 아님 | D · CHLG-03 |

## 테이블별 쓰기 권한

| 테이블 | 쓰기 (INSERT/UPDATE) | 읽기 | 담당 영역 | 비고 |
| --- | --- | --- | --- | --- |
| users | 배수빈 (A) | 전원 | 회원·인증 | XP 지급은 A가 grant_xp()로 제공. D가 직접 UPDATE 하지 않는다 |
| health_records | 최병주 (C) | 홍서윤 (B) · 김이경 (D) | 건강정보 | B는 예측 입력으로, D는 진단 질환의 챌린지 추천·실측 위협도 산출로 읽는다. D가 의존하는 필드는 아래 '읽기 계약' 참고 |
| predictions | 홍서윤 (B) | 최병주 (C) · 김이경 (D) | 예측 | C는 대시보드 추이, D는 추천 근거로 읽는다 |
| prediction_contributions | 홍서윤 (B) | 김이경 (D) | 예측 | D는 factor_key로 챌린지를 매칭할 때 읽는다 |
| monsters | 김이경 (D) | 전원 | 도감 | 마스터 데이터. 시드로 관리하고 운영 중 변경 없음 |
| user_monsters | 김이경 (D) | — | 도감 | 위협도 갱신은 B가 예측 저장 직후 refresh_impact_from_prediction()을 호출해 D가 쓴다 |
| challenges | 김이경 (D) | — | 챌린지 | 마스터 데이터 |
| user_challenges | 김이경 (D) | — | 챌린지 |  |
| challenge_logs | 김이경 (D) | — | 챌린지 | XP 지급은 grant_xp() 호출 결과를 xp_granted에 기록 |
| challenge_recommendations | 김이경 (D) | — | 챌린지 |  |
| rewards | 김이경 (D) | — | 보상 | 마스터 데이터 |
| user_rewards | 김이경 (D) | — | 보상 |  |
| ※ 이 표에 없는 조합으로 남의 테이블에 쓰기가 필요해지면, 직접 쓰지 말고 채널에 올려주세요. 규칙을 고치거나 함수를 새로 만듭니다. |  |  |  |  |
| 읽기 계약 — D가 health_records에서 읽는 필드 (C는 이 필드를 바꿀 때 D에 알려주세요) |  |  |  |  |
| fasting_glucose · hba1c (스파이크 실측 위협도) · smoking_current · alcohol_frequency · alcohol_amount · bmi · waist_cm · walking_days · walking_minutes · strength_days · sitting_minutes · dining_out_freq (진단자 추천 매칭) · recorded_at (최신 1건 선택) |  |  |  |  |

## 모듈 간 호출 규약

| 함수 | 제공 | 호출 | 호출 시점 | 인자 | 반환 |
| --- | --- | --- | --- | --- | --- |
| grant_xp() | 배수빈 (A) | 김이경 (D) | 챌린지 로그가 reward_eligible=TRUE로 저장된 직후 | user_id, amount, source('challenge'\|'seal'\|'bonus') | { level_up: bool, new_level: int, total_xp: int } |
| refresh_impact_from_prediction() | 김이경 (D) | 홍서윤 (B) | predictions와 prediction_contributions 저장이 끝난 직후. 미진단 질환 경로 | user_id, prediction_id | { updated: int, sealed: [monster_code] } |
| refresh_impact_from_health_record() | 김이경 (D) | 최병주 (C) | health_records 저장이 끝난 직후. 항상 호출한다 — 질환별 진단 여부 분기는 D 내부에서 한다 | user_id, health_record_id | { updated: int, sealed: [monster_code] } |
| get_top_contributions() | 홍서윤 (B) | 김이경 (D) | 미진단 질환의 챌린지 추천 카드 3장을 만들 때 | prediction_id, disease, limit | [{ factor_key, contribution, direction, rank }] |
| get_global_importance() | 홍서윤 (B) | 김이경 (D) | 진단 질환의 챌린지 추천·위협도 산출. 모델 버전당 고정값이라 캐시 가능 | disease, limit | [{ factor_key, importance, normalized_score, rank, model_version }] |
| ※ 함수 시그니처가 바뀌면 제공하는 쪽이 채널에 먼저 올립니다. 호출하는 쪽이 먼저 바꾸지 않습니다. |  |  |  |  |  |

## A · 회원·인증 · 11개

담당 배수빈 · 작성 완료 2026-09-28

### AUTH-01 · 이메일 중복 확인

`GET /api/v1/auth/check-email`

- **인증**: 불필요
- **요청 파라미터**: ?email=str
- **요청 본문**: —
- **응답 (성공)**: { available: true }
- **주요 에러**: VALIDATION_ERROR
- **관련 요구사항**: REQ-USER-001
- **사용 테이블**: users 읽기
- **상태**: 작성

### AUTH-02 · 회원가입

`POST /api/v1/auth/signup`

- **인증**: 불필요
- **요청 파라미터**: —
- **요청 본문**: email, password, nickname, birth_year, sex, height_cm, motivation_type, dm_diagnosed, htn_diagnosed, dm_medication, htn_medication, disclaimer_agreed
- **응답 (성공)**: { user_id, access_token, refresh_token }
- **주요 에러**: AUTH_EMAIL_DUPLICATED, AUTH_WEAK_PASSWORD, VALIDATION_ERROR
- **관련 요구사항**: REQ-USER-001·002·007·008·010
- **사용 테이블**: users 쓰기
- **상태**: 작성

### AUTH-03 · 로그인

`POST /api/v1/auth/login`

- **인증**: 불필요
- **요청 파라미터**: —
- **요청 본문**: email, password
- **응답 (성공)**: { access_token, refresh_token, user: { id, nickname, level, total_xp } }
- **주요 에러**: AUTH_INVALID_CREDENTIALS, AUTH_ACCOUNT_LOCKED
- **관련 요구사항**: REQ-USER-003·004
- **사용 테이블**: users 쓰기 (login_fail_count, locked_until)
- **상태**: 작성

### AUTH-04 · 토큰 재발급

`POST /api/v1/auth/refresh`

- **인증**: Refresh 토큰
- **요청 파라미터**: —
- **요청 본문**: refresh_token
- **응답 (성공)**: { access_token }
- **주요 에러**: AUTH_TOKEN_EXPIRED, AUTH_TOKEN_INVALID
- **관련 요구사항**: NFR-SEC-001
- **사용 테이블**: —
- **상태**: 작성

### AUTH-05 · 로그아웃

`POST /api/v1/auth/logout`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: —
- **응답 (성공)**: { success: true }
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-USER-005
- **사용 테이블**: — (Refresh 토큰 무효화)
- **상태**: 작성

### USER-01 · 내 정보 조회

`GET /api/v1/users/me`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: —
- **응답 (성공)**: { id, email, nickname, birth_year, sex, height_cm, motivation_type, dm_diagnosed, htn_diagnosed, dm_medication, htn_medication, level, total_xp }
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-USER-006
- **사용 테이블**: users 읽기
- **상태**: 작성

### USER-02 · 내 정보 수정

`PATCH /api/v1/users/me`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: nickname?, height_cm?, motivation_type?
- **응답 (성공)**: { 수정된 내 정보 }
- **주요 에러**: VALIDATION_ERROR, UNAUTHORIZED
- **관련 요구사항**: REQ-USER-006·008
- **사용 테이블**: users 쓰기
- **상태**: 작성

### USER-03 · 진단·복약 이력 수정

`PATCH /api/v1/users/me/diagnosis`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: dm_diagnosed, htn_diagnosed, dm_medication, htn_medication
- **응답 (성공)**: { dm_diagnosed, htn_diagnosed, dm_medication, htn_medication, prediction_enabled } ※ prediction_enabled는 두 질환을 모두 진단받은 경우에만 false (기획서 v19 2.3)
- **주요 에러**: VALIDATION_ERROR
- **관련 요구사항**: REQ-USER-007
- **사용 테이블**: users 쓰기
- **상태**: 작성

### USER-04 · 비밀번호 변경

`PATCH /api/v1/users/me/password`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: current_password, new_password
- **응답 (성공)**: { success: true }
- **주요 에러**: AUTH_INVALID_CREDENTIALS, AUTH_WEAK_PASSWORD
- **관련 요구사항**: REQ-USER-002
- **사용 테이블**: users 쓰기
- **상태**: 작성

### USER-05 · 회원 탈퇴

`DELETE /api/v1/users/me`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: password
- **응답 (성공)**: { success: true, purge_at: "2026-10-28" }
- **주요 에러**: AUTH_INVALID_CREDENTIALS
- **관련 요구사항**: REQ-USER-009
- **사용 테이블**: users 쓰기 (status=withdrawn, withdrawn_at)
- **상태**: 작성

### USER-06 · 레벨·경험치 조회

`GET /api/v1/users/me/level`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: —
- **응답 (성공)**: { level, total_xp, next_level_xp }
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-RECO-003
- **사용 테이블**: users 읽기
- **상태**: 작성 (레벨 공식 미정)

## B · 예측·모델 · 3개

담당 홍서윤 · 확정 2026-10-01

### PRED-01 · 예측 접수

`POST /api/v1/predictions`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: health_record_id(필수). 서버가 소유권과 질환별 진단·약물 이력을 확인하고, 미진단 질환만 큐에 넣는다. 둘 다 진단이면 PRED_ALL_DIAGNOSED. 입력은 불변 health_records에서 읽는다
- **응답 (성공)**: HTTP 202 { success:true, data:{ prediction_id, job_id, status:"pending", model_version, poll_url:"/api/v1/predictions/{prediction_id}" } }. 폴링은 PRED-02 사용
- **주요 에러**: PRED_ALL_DIAGNOSED(400), HLTH_RECORD_NOT_FOUND(404), HLTH_PROFILE_INCOMPLETE(400), PRED_INPUT_INSUFFICIENT(400), VALIDATION_ERROR(400), UNAUTHORIZED(401), INTERNAL_ERROR(500)
- **관련 요구사항**: REQ-PRED-001·002·007·008 · NFR-PERF-002
- **사용 테이블**: users 읽기 / health_records 읽기 / predictions 쓰기 / Redis enqueue
- **상태**: 확정 — 홍서윤 10/1

### PRED-02 · 예측 상태·결과 조회

`GET /api/v1/predictions/{prediction_id}`

- **인증**: 필요
- **요청 파라미터**: prediction_id(양의 정수)
- **요청 본문**: —
- **응답 (성공)**: HTTP 200 { success:true, data:{ prediction_id, job_id, status:"pending"\|"done"\|"failed", model_version, results?: [{ disease, probability }], failure?: { code, message, retryable } } }. pending일 때 results 필드 생략. 완료 결과는 미진단 질환만 포함. grade 경계는 팀 검증 후 확정
- **주요 에러**: NOT_FOUND(404), UNAUTHORIZED(401), INTERNAL_ERROR(500)
- **관련 요구사항**: REQ-PRED-002·003·004·006·007·009 · NFR-REL-001
- **사용 테이블**: predictions 읽기 / users·health_records 읽기 (본인 소유·진단 분기)
- **상태**: 확정 — 홍서윤 10/1

### PRED-03 · 기여요인 조회

`GET /api/v1/predictions/{prediction_id}/contributions`

- **인증**: 필요
- **요청 파라미터**: prediction_id(양의 정수), disease=diabetes\|hypertension(선택), limit=1~100(기본 100; 화면은 3 지정)
- **요청 본문**: —
- **응답 (성공)**: HTTP 200 { success:true, data:{ prediction_id, status:"pending"\|"done"\|"failed", disease, model_version, factor_dictionary_version, contribution_unit:"probability", items:[{ factor_key, contribution, direction, rank, modifiable }] } }. pending/failed 상태에는 items 생략; done이면 지원 factor 전량(0 포함). disease 생략 시 예측에 포함된 모든 미진단 질환 반환
- **주요 에러**: NOT_FOUND(404), VALIDATION_ERROR(400), UNAUTHORIZED(401), INTERNAL_ERROR(500)
- **관련 요구사항**: REQ-PRED-005 · REQ-CHLG-001 · NFR-MODL-002
- **사용 테이블**: predictions 읽기 / prediction_contributions 읽기
- **상태**: 확정 — 홍서윤 10/1

## C · 건강정보·대시보드 · 6개

담당 최병주 · 공통 인증·응답 규칙은 공통 탭 적용

### HLTH-01 · 건강정보 입력·시점별 저장

`POST /api/v1/health-records`

- **인증**: 필요
- **요청 파라미터**: — (토큰 사용자 기준)
- **요청 본문**: 간편(simple, 최근 4주): weight_kg, waist_cm, smoking_current, alcohol_frequency, alcohol_amount(음주 시), walking_days, walking_minutes, strength_days, sitting_minutes, family_history_dm, family_history_htn, dining_out_freq(1~7). birth_year·sex·height_cm은 A users 프로필에서 입력·수정하고 C 화면에서 확인한다(누락 시 저장/예측 불가). bmi는 height_cm·weight_kg로 서버 계산. 정밀(detail): 간편값 + sbp, dbp, fasting_glucose, hba1c, triglyceride, hdl(6항목 선택). total_cholesterol은 현재 사용자 입력에서 제외.
- **응답 (성공)**: { health_record_id, input_mode, recorded_at, bmi } (201)
- **주요 에러**: HLTH_PROFILE_INCOMPLETE(400: birth_year·sex·height_cm 누락), HLTH_VALUE_OUT_OF_RANGE(400: 허용 범위 포함), VALIDATION_ERROR, UNAUTHORIZED
- **관련 요구사항**: REQ-HLTH-001·002·003·004
- **사용 테이블**: users 읽기(A AUTH-02·USER-02에서 기본정보 입력/수정), health_records 쓰기(C); 저장 후 D refresh_impact_from_health_record() 호출. B 예측 요청은 별도
- **상태**: 제출안 · 식생활 확정 저장 필드는 dining_out_freq. v7 채소 빈도·야식·단 음료·식사 규칙성은 v8-1/ERD에 저장 필드가 없어 확장 제안; 채택 시 요구사항·테이블·B 모델 매핑 동시 개정

### HLTH-02 · 건강기록 목록·기간 조회

`GET /api/v1/health-records`

- **인증**: 필요
- **요청 파라미터**: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&page=1&size=20 (최근 12개월)
- **요청 본문**: —
- **응답 (성공)**: { items:[{ health_record_id, recorded_at, input_mode, weight_kg, waist_cm, bmi, sbp, dbp, fasting_glucose, hba1c, triglyceride, hdl, ...생활습관 필드 }], total, page, size }
- **주요 에러**: VALIDATION_ERROR, UNAUTHORIZED
- **관련 요구사항**: REQ-HLTH-004·005
- **사용 테이블**: health_records 읽기 (본인 기록만, recorded_at 내림차순)
- **상태**: 제출안(원본 기록을 덮어쓰지 않음)

### HLTH-03 · 챌린지 PHOTO 증빙 업로드

`POST /api/v1/evidence/photos`

- **인증**: 필요
- **요청 파라미터**: — (토큰 사용자 기준)
- **요청 본문**: multipart/form-data: photo(필수), user_challenge_id(필수). 본인의 활성 PHOTO 챌린지에 한해 업로드. JPEG/PNG, 최대 10 MiB(제출 설계값). AI 분석·음식 성분 추정 없음.
- **응답 (성공)**: { evidence_url, uploaded_at } (201). evidence_url은 공개 정적 URL이 아닌 비공개 증빙 참조값.
- **주요 에러**: VALIDATION_ERROR(형식·크기 포함), UNAUTHORIZED, CHLG_NOT_ACTIVE
- **관련 요구사항**: REQ-CHLG-008·REQ-USER-009·NFR-SEC-005
- **사용 테이블**: C: 사진을 비공개 저장하고 evidence_url 반환. D CHLG-07: 소유권 확인 후 challenge_logs.evidence_url 기록·수행 증빙. 사진 AI 판정 없음.
- **상태**: 제출안(MVP는 업로드 → 비공개 저장 → evidence_url 기록 → 수행 증빙까지만. 음식 사진 분석·AI 성공 판정은 2차 범위)

### DASH-01 · 대시보드 현재 위험도 요약

`GET /api/v1/dashboard/summary`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: —
- **응답 (성공)**: { prediction_available, risks:[{ disease, probability, grade, delta, predicted_at }], latest_health_record:{ health_record_id, recorded_at } \| null }
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-DASH-001·REQ-PRED-007
- **사용 테이블**: predictions·health_records 읽기 (완료 예측만); 모델 계산 없음
- **상태**: 제출안(risks는 미진단 질환만 포함 — 둘 다 진단이거나 예측 전일 때만 []; B 결과 형식 확인)

### DASH-02 · 위험도·건강수치 동일 기간 추이

`GET /api/v1/dashboard/trends`

- **인증**: 필요
- **요청 파라미터**: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD (최근 12개월)
- **요청 본문**: —
- **응답 (성공)**: { points:[{ recorded_at, health_record_id, measurements:{ weight_kg, waist_cm, sbp, dbp, fasting_glucose, hba1c }, risks:[{ disease, probability, predicted_at }] }] }
- **주요 에러**: VALIDATION_ERROR, UNAUTHORIZED
- **관련 요구사항**: REQ-DASH-002
- **사용 테이블**: health_records·predictions 읽기 (health_record_id로 연결, 완료 예측만)
- **상태**: 제출안(B 예측 이력 형식·표시 지표 확인)

### DASH-03 · 대시보드 챌린지 주간 현황

`GET /api/v1/dashboard/challenges`

- **인증**: 필요
- **요청 파라미터**: ?week_start=YYYY-MM-DD
- **요청 본문**: —
- **응답 (성공)**: { week_start, active_count, weekly_completion_rate, items:[{ user_challenge_id, title, progress_rate }] }
- **주요 에러**: VALIDATION_ERROR, UNAUTHORIZED
- **관련 요구사항**: REQ-DASH-003
- **사용 테이블**: D CHLG-06·CHLG-08 조회 결과 재사용; D 테이블 직접 접근 없음
- **상태**: 제출안(D 주간 달성률 산식 확인)

## D · 챌린지·보상·도감 · 11개

담당 김이경 · 작성 완료 2026-09-29

### CHLG-01 · 추천 생성

`POST /api/v1/challenge-recommendations/generate`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: —
- **응답 (성공)**: { items: [{ recommendation_id, challenge_id, title, factor_key, factor_score, rank, difficulty, verification_type, context_label }], total } ※ factor_score는 0~100 개인화 점수. 미진단 질환은 개인 SHAP normalized_score, 진단 질환은 global normalized_score × behavior_weight를 사용. factor별 behavior_weight 변환 기준은 2주차 모델 1회전 후 확정.
- **주요 에러**: CHLG_RECOMMENDATION_UNAVAILABLE, PRED_NOT_FOUND, UNAUTHORIZED
- **관련 요구사항**: REQ-CHLG-001·002
- **사용 테이블**: predictions·prediction_contributions 읽기 / challenges 읽기 / challenge_recommendations 쓰기
- **상태**: 작성

### CHLG-02 · 추천 카드 조회

`GET /api/v1/challenge-recommendations`

- **인증**: 필요
- **요청 파라미터**: ?page=1&size=20
- **요청 본문**: —
- **응답 (성공)**: { items: [{ recommendation_id, challenge_id, title, description, factor_key, rank, difficulty, verification_type, context_label, action, cooldown_choice, exclude_until }], total, page, size }
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-CHLG-001·002·006
- **사용 테이블**: challenge_recommendations·challenges 읽기
- **상태**: 작성

### CHLG-03 · 추천 거절·해당없음/쿨다운 설정

`PATCH /api/v1/challenge-recommendations/{recommendation_id}`

- **인증**: 필요
- **요청 파라미터**: path: recommendation_id
- **요청 본문**: action='rejected'\|'not_applicable', cooldown_choice? ('7d'\|'30d'\|'until_manual', rejected일 때만)
- **응답 (성공)**: { recommendation_id, action, consecutive_reject_count, cooldown_choice, exclude_until, suppressed_until_manual }
- **주요 에러**: CHLG_RECOMMENDATION_NOT_FOUND, CHLG_INVALID_COOLDOWN
- **관련 요구사항**: REQ-CHLG-006
- **사용 테이블**: challenge_recommendations 쓰기
- **상태**: 작성

### CHLG-04 · 수동 제외 해제

`PATCH /api/v1/challenge-recommendations/{recommendation_id}/unsuppress`

- **인증**: 필요
- **요청 파라미터**: path: recommendation_id
- **요청 본문**: —
- **응답 (성공)**: { recommendation_id, suppressed_until_manual: false }
- **주요 에러**: CHLG_RECOMMENDATION_NOT_FOUND
- **관련 요구사항**: REQ-CHLG-006
- **사용 테이블**: challenge_recommendations 쓰기
- **상태**: 작성

### CHLG-05 · 챌린지 시작

`POST /api/v1/user-challenges`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: recommendation_ids: [int] (1~3개), safety_confirmed?: boolean ※ 운동형 챌린지가 포함된 경우 true 필수. 비운동형만 포함되면 생략 가능
- **응답 (성공)**: { items: [{ user_challenge_id, challenge_id, status, start_date, end_date, daily_target_count, target_value, duration_days }], active_count }
- **주요 에러**: CHLG_LIMIT_EXCEEDED, CHLG_RECOMMENDATION_NOT_FOUND, CHLG_ALREADY_ACTIVE, CHLG_SAFETY_CONFIRMATION_REQUIRED, VALIDATION_ERROR
- **관련 요구사항**: REQ-CHLG-002 · REQ-CHLG-010
- **사용 테이블**: challenge_recommendations 쓰기(accepted·거절횟수 초기화) / challenges 읽기 / user_challenges 쓰기
- **상태**: 작성

### CHLG-06 · 진행 중 챌린지 조회

`GET /api/v1/user-challenges`

- **인증**: 필요
- **요청 파라미터**: ?status=active&page=1&size=20
- **요청 본문**: —
- **응답 (성공)**: { items: [{ user_challenge_id, challenge_id, title, factor_key, difficulty, verification_type, context_type, context_label, start_date, end_date, completed_count, daily_target_count, progress_rate }], total, page, size }
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-CHLG-003·004·005
- **사용 테이블**: user_challenges·challenges·challenge_logs 읽기
- **상태**: 작성

### CHLG-07 · 챌린지 수행 기록

`POST /api/v1/user-challenges/{user_challenge_id}/logs`

- **인증**: 필요
- **요청 파라미터**: path: user_challenge_id
- **요청 본문**: occurred_at, context_slot?, value?, verification_method, evidence_url? ※ photo는 C 업로드 경로에서 반환된 비공개 증빙 위치값 사용
- **응답 (성공)**: { log_id, result, verification_status, reward_eligible, xp_granted, weekly_progress, level_up, new_level, reward? }
- **주요 에러**: CHLG_NOT_ACTIVE, CHLG_LOG_DUPLICATED, CHLG_VERIFICATION_FAILED, VALIDATION_ERROR
- **관련 요구사항**: REQ-CHLG-003·004·007·008 · REQ-RECO-003·004 · REQ-PRED-011
- **사용 테이블**: user_challenges·challenges 읽기 / challenge_logs·user_monsters·user_rewards 쓰기 / A grant_xp() 호출
- **상태**: 작성

### CHLG-08 · 수행 기록 조회

`GET /api/v1/user-challenges/{user_challenge_id}/logs`

- **인증**: 필요
- **요청 파라미터**: path: user_challenge_id, ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&page=1&size=20
- **요청 본문**: —
- **응답 (성공)**: { items: [{ log_id, log_date, occurred_at, sequence_no, context_slot, value, unit, result, verification_method, verification_status, reward_eligible, xp_granted }], total, page, size }
- **주요 에러**: CHLG_NOT_FOUND
- **관련 요구사항**: REQ-CHLG-003·004
- **사용 테이블**: user_challenges·challenge_logs 읽기
- **상태**: 작성

### CHLG-09 · 챌린지 중단

`POST /api/v1/user-challenges/{user_challenge_id}/stop`

- **인증**: 필요
- **요청 파라미터**: path: user_challenge_id
- **요청 본문**: stop_reason?
- **응답 (성공)**: { user_challenge_id, status: 'abandoned', stopped_at, stop_reason }
- **주요 에러**: CHLG_NOT_ACTIVE, CHLG_NOT_FOUND
- **관련 요구사항**: REQ-CHLG-005
- **사용 테이블**: user_challenges 쓰기
- **상태**: 작성

### MNSTR-01 · 내 위험요인 도감 조회

`GET /api/v1/monsters/me`

- **인증**: 필요
- **요청 파라미터**: —
- **요청 본문**: —
- **응답 (성공)**: { items: [{ monster_id, code, name, title, disease_scope, impact_score, state, weekly_progress, progress_week_start, sealed_at, seal_count, impact_source }] } ※ state: rage \| caution \| stable \| not_contributing \| resolved \| sealed \| unmeasured. 공략 대상은 rage·caution·stable만. not_contributing은 '현재 위험 기여 없음', resolved는 '요인 해소됨'으로 표시.
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-CHLG-007 · REQ-RECO-005 · REQ-PRED-010·011
- **사용 테이블**: monsters·user_monsters 읽기
- **상태**: 작성

### RWRD-01 · 내 보상 조회

`GET /api/v1/rewards/me`

- **인증**: 필요
- **요청 파라미터**: ?page=1&size=20
- **요청 본문**: —
- **응답 (성공)**: { items: [{ reward_id, code, name, motivation_type, reward_kind, item_level, acquired_at }], total, page, size }
- **주요 에러**: UNAUTHORIZED
- **관련 요구사항**: REQ-RECO-001·002·004
- **사용 테이블**: user_rewards·rewards 읽기
- **상태**: 작성
