# B 예측 API 명세

지정 API 시트의 공통 규칙 및 B · 예측·모델 탭 6~8행에 확정한 3개 API를 정리했다. 시트 셀은 2026-10-01에 갱신했다. 아래 내용은 서비스 구현 완료가 아닌 API 계약이다.

## 공통 계약

Base path `/api/v1`. `Authorization: Bearer <access_token>` 필수. user_id는 토큰에서만 얻는다. body/query/path에 user_id를 받지 않는다. 원본 공통 규칙에 따라 성공은 `{"success":true,"data":{...}}`, 실패는 `{"success":false,"error":{"code":"...","message":"..."}}`로 반환한다. 반대쪽 data/error의 null 키는 추가하지 않는다. 모든 응답 헤더에 `X-Request-Id`를 넣는다. 시각은 KST(Asia/Seoul) ISO 8601로 +09:00 오프셋을 붙인다, JSON 키는 snake_case, 확률은 0~1, 결과 변화량은 percentage points다. 잘못된 JSON·요청 형식·필수값·범위 검증은 공통 규칙의 `VALIDATION_ERROR` 400을 사용한다.

| ID | Method | Endpoint | 목적 | 성공 |
|---|---|---|---|---|
| PRED-01 | POST | /api/v1/predictions | 비동기 예측 접수 | 202 |
| PRED-02 | GET | /api/v1/predictions/{prediction_id} | 작업 상태·결과 조회·폴링 | 200 |
| PRED-03 | GET | /api/v1/predictions/{prediction_id}/contributions | 질환별 기여도 조회 | 200 |

서버가 건강기록과 예측의 소유자를 검증한다. 타인 리소스는 존재 여부와 상관없이 404다. 403을 주면 그 ID가 있다는 사실이 드러나 건강 데이터가 샌다. 인증 오류를 먼저 검사한다. 작업ID를 알더라도 소유권 검사를 생략하지 않는다. 인증 없는 캐시와 개인별 응답 공유를 금지한다.

## PRED-01 예측 접수

요청:
```json
{"health_record_id":101}
```
필수: health_record_id(양의 정수). C가 저장한 불변 건강기록만 받는다. 필수 입력 목록은 [모델 계약](../03_ai_data/model.md)을 따른다. age/sex/height 등 users 기본값도 예측 시점에 스냅샷으로 고정한다. 클라이언트가 model_version, 확률, SHAP 또는 진단자 여부를 지정하지 않는다.

검사 순서는 토큰 → 건강기록 소유권 → 질환별 진단/약물 상태 → 필수 feature·단위 → 활성 모델 artifact → 접수다. 진단·약물 이력이 있는 질환만 건너뛰고 미진단 질환은 계속 처리한다. 둘 다 진단됐을 때만 PRED_ALL_DIAGNOSED로 접수를 거절한다. 진단 여부가 미확인인 질환은 미진단으로 간주하지 않는다. 누락 feature는 전부 반환하고 추론을 시작하지 않는다.

성공 예시(설명용):
```json
{"success":true,"data":{"prediction_id":501,"job_id":"job-example-501","status":"pending","model_version":"MODEL_VERSION","poll_url":"/api/v1/predictions/501","created_at":"2026-09-28T05:00:00Z"}}
```

1초 내 접수를 목표로 한다. HTTP 202를 반환한다. 이는 요청을 접수해 비동기 처리 중이라는 뜻이며 추론 완료를 뜻하지 않는다. B가 predictions pending을 만들고 확정한 model_version과 입력 스냅샷을 저장한다. 큐에는 prediction_id/job_id와 최소 작업 메타데이터만 전달하고 개인정보 전체를 로그에 찍지 않는다. ai_worker가 추론·기여도 계산을 수행한다. 큐 적재가 실패하면 failed를 기록하고 500으로 응답하여 영구 pending을 만들지 않는다. DB-큐 사이의 유실 복구 전략은 아래 구현 항목에 명시한다.

HTTP 요청 재시도는 별도 예측을 만들 수 있다. 클라이언트는 연속 제출을 막고, 받은 prediction_id로 상태를 조회한다. 큐의 같은 job 재전달은 아래 저장·워커 계약에 따라 멱등 처리한다. 공통 규칙에 없는 Idempotency-Key 헤더는 이번 확정 요청 계약에 넣지 않는다.

| 코드 | HTTP | 조건 |
|---|---|---|
| UNAUTHORIZED | 401 | 토큰 없음·만료·무효 |
| PRED_ALL_DIAGNOSED | 400 | 당뇨·고혈압이 모두 진단·복약 상태여서 예측 대상 없음 |
| PRED_DIAGNOSIS_HISTORY_REQUIRED | 400 | 해당 질환의 진단·약물 이력 미확인 |
| NOT_FOUND | 404 | 기록·예측 없음, 타인 리소스 포함 |
| PRED_INPUT_INSUFFICIENT | 400 | 필수 모델 입력 누락; message에 누락 목록 |
| VALIDATION_ERROR | 400 | JSON·path·query 필수값·형식·범위 오류 |
| PRED_MODEL_UNAVAILABLE / PRED_QUEUE_UNAVAILABLE | 500 | 서버 모델·큐 준비 오류 |
| INTERNAL_ERROR | 500 | 그 외 서버 오류 |


누락 예시:
```json
{"success":false,"error":{"code":"PRED_INPUT_INSUFFICIENT","message":"필수 입력이 누락되었습니다: 허리둘레(waist_cm), 좌식시간(sitting_minutes)."}}
```
실제로 필수인 목록은 활성 모델 manifest로 고정한다. 좌식 feature 미채택 모델에서는 sitting_minutes를 모델의 필수값이라고 거절하지 않는다. C의 설문 필수 여부와 모델 필수 여부는 구분한다.

## PRED-02 상태와 결과 조회

값이 없는 필드는 null 로 싣지 않고 아예 뺀다. pending·failed 응답에 results 를, pending·done 응답에 failure 를 넣지 않는다.

path: prediction_id(양의 정수). poll 간격은 최초 1초, 장기 pending은 점진적 증가를 권고한다. 상태 ENUM은 ERD와 같은 pending/done/failed 세 가지다. worker 실행 중에도 pending이다.

pending:
```json
{"success":true,"data":{"prediction_id":501,"job_id":"job-example-501","status":"pending","model_version":"MODEL_VERSION"}}
```

done(모든 수치는 설명용 가상 예시; 미확정 등급은 응답하지 않음):
```json
{"success":true,"data":{"prediction_id":501,"job_id":"job-example-501","health_record_id":101,"status":"done","model_version":"MODEL_VERSION","predicted_at":"2026-09-28T05:00:02Z","results":[{"disease":"diabetes","probability":0.31},{"disease":"hypertension","probability":0.22}],"notice":"의료 진단이 아닌 참고용입니다."}}
```

probability는 계약 형식을 보이는 가상 수치다. 이 응답에는 팀이 정하지 않은 등급, 직전값·변화량, 이력 및 대사증후군 결과를 추가하지 않는다. 값이 필요해지면 정책과 응답 필드를 API 시트에서 먼저 확정한다.

실패 요청을 기존 최신 성공 결과로 덮어쓰지 않는다. API가 반환하는 DB의 질환별 컬럼은 HTTP에서는 disease 배열로 변환한다(NFR-SCAL-001).

대사증후군 판정은 실측 다섯 지표의 별도 규칙이다. '분노 캐릭터 3개'로 계산하지 않는다. 공식 판정 기준·복약·누락 정책이 확정되지 않으면 unavailable를 반환한다. 규칙이 확정되고 모든 필요한 입력이 있을 때만 evaluated/count를 반환한다. 신규 진단이나 의료 조언으로 표현하지 않는다.

failed:
```json
{"success":true,"data":{"prediction_id":501,"job_id":"job-example-501","status":"failed","failure":{"code":"PRED_INFERENCE_FAILED","message":"예측에 실패했습니다. 다시 시도해주세요.","retryable":true}}}
```
조회 자체는 성공했으므로 HTTP 200/success=true이고 작업 실패는 failure로 전달한다. worker exception stack·경로·원시 건강값은 노출하지 않는다. `failure` 상세 저장 위치는 기존 ERD에 없으므로 Redis 보존 정책 또는 B 컬럼 확장을 A/C와 협의한다. 30초는 추론 목표이며 곧바로 실패로 바꾸는 하드 timeout 값은 아니다. 별도 hard timeout·복구 작업 설정을 운영 계약에 둔다.

## PRED-03 기여도 조회

query: `disease=diabetes|hypertension` 선택, `limit` 기본 100, 1~100. disease를 생략하면 예측에 포함된 모든 미진단 질환의 기여도를 반환한다. 요청한 prediction이 pending 또는 failed이면 200으로 현재 상태를 반환하고 items를 생략한다. done이면 저장된 결과를 반환한다.

```json
{"success":true,"data":{"prediction_id":501,"status":"done","disease":"diabetes","model_version":"MODEL_VERSION","factor_dictionary_version":"v0.1-sedentary","contribution_unit":"probability","items":[{"factor_key":"age","contribution":0.05,"direction":"increase","rank":1,"modifiable":false},{"factor_key":"bmi_high","contribution":0.03,"direction":"increase","rank":2,"modifiable":true},{"factor_key":"sedentary_time_high","contribution":0.02,"direction":"increase","rank":3,"modifiable":true}]}}
```
값은 형식 설명용이며 학습 결과가 아니다. SHAP 산식·direction/rank는 [모델 계약](../03_ai_data/model.md)을 따른다. 지원되는 매핑 factor 전량을 0 포함 저장한다. `limit=3`이면 상위 3개만 응답할 수 있지만 기본 limit=100은 D 추천에 전체 근거를 제공한다. top3 합이 전체 확률과 같다고 해석하지 않는다. 위협도나 공략 점수는 이 API의 raw contribution에 섞지 않는다. global importance는 진단자 내부 추천용 함수이며 별도의 공개 위험도 API로 만들지 않는다.

## 저장·워커 계약

- B writer: predictions, prediction_contributions. 읽기: 필요한 users/health_records. D 테이블은 D 함수로만 변경한다.
- worker 성공 시 해당되는 미진단 질환 결과와 **전체** factor 기여도를 하나의 transaction으로 저장한 뒤 done 전환. 두 질환 중 하나 실패 시 부분 결과를 done으로 게시하지 않는다.
- 동일 job 재전달 시 완료행·기여도를 중복 생성하지 않는다. prediction row lock 및 `(prediction_id,disease,factor_key)` 중복 방지 전략을 사용한다. DB UNIQUE 추가는 A와 합의한다.
- 커밋 후 refresh_impact_from_prediction 호출. 호출 오류는 위협도 동기화 재시도로 분리한다. 사용자에게 저장된 예측까지 실패했다고 알리지 않는다.
- 오래된 작업이 늦게 완료돼도 '최신 입력/예측'을 덮어쓰지 않도록 D의 근거 ID 비교가 필요하다.
- 모든 라우트의 공통 validation/exception wrapper, 진단 플래그 모델, 건강기록 모델, 예측 ORM은 현재 템플릿에 없는 후속 구현이다.

## 수용 사례

| 사례 | 기대 결과 |
|---|---|
| 본인 정상 입력 | 202 pending, job_id + prediction_id |
| 타인 record/예측 | 404, 큐·개인결과 접근 없음 |
| 한 질환 진단/복약 | 해당 질환만 결과에서 생략, 다른 미진단 질환은 예측 |
| 두 질환 모두 진단/복약 | 400 PRED_ALL_DIAGNOSED, prediction 생성 없음 |
| 필수 누락 | PRED_INPUT_INSUFFICIENT, 누락 목록, 추론 없음 |
| pending 조회 | 200 pending, results 없음 |
| 같은 job 중복 소비 | 결과·기여도 한 세트 |
| worker 오류 | failed, 이전 성공 이력 보존 |
| D 위협도 갱신 오류 | prediction done 유지, 갱신 재시도 |
| 좌식 포함 모델 | 독립 factor, 활동 factor와 중복 합산 없음 |
| 실측 혈당 미입력 | 스파이크 measured 미측정, 가짜 SHAP 없음 |

## 요구사항 추적

PRED-01: REQ-PRED-001/002/007/008, REQ-USER-007, NFR-PERF-002, NFR-SEC-001/002.
PRED-02: REQ-PRED-003/004/006/009/010/011, NFR-REL-001, NFR-SCAL-001.
PRED-03: REQ-PRED-005, REQ-CHLG-001, NFR-MODL-002.
공통: REQ-COMN-001/002, NFR-COMP-001.

## 원본 대조 기록

- 공통 규칙 C10:C11의 응답 형식, C13의 상태 코드, C15:C17의 오류 명명, C19의 전체 경로, C26의 응답 추적 헤더를 적용했다.
- 모듈 간 호출 F8/F9의 내부 함수 반환은 배열이다. 공개 HTTP 기여도 응답의 metadata/data wrapper와 구분한다.
- 쓰기 권한 E10에는 옛 함수명 refresh_monster_hp가 남아 있지만, 모듈 간 호출 A6 및 최신 Slack 답변의 refresh_impact_from_prediction을 따른다. 타 담당자의 원본 탭은 임의 수정하지 않는다.

## 원본

[지정 API 시트 — B 탭](https://docs.google.com/spreadsheets/d/1YGAncv-rZBLBvrVFjlk7yg1kP7fabZunzYmOZz8C9OE/edit?gid=1286618417#gid=1286618417)
· [최신 모듈 계약 변경](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790570304697439)
· [요구사항 v8](https://2026-ndc9438.slack.com/archives/C0C3FK3311C/p1790150890169639)
