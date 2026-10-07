# D 위협도 갱신 전달안 — 2026-10-07

기준 main: 179f59b6895af7eb7b332d13d127ed0bfead5cc7 (#29 머지).
상태: 구현·로컬 검증 완료, 정책 합의와 MySQL CI 확인을 기다리는 Draft 전달안.

## 제공 함수와 연결 위치

`app.services.impacts`에서 아래 함수를 제공한다. 기존 모듈 호출 계약의 인자·반환을 유지한다.

```python
from app.services.impacts import refresh_impact_from_health_record, refresh_impact_from_prediction

await refresh_impact_from_health_record(user_id, health_record_id)
await refresh_impact_from_prediction(user_id, prediction_id)
# 두 함수 반환: {"updated": int, "sealed": list[str]}
```

1. C의 simple/detail 건강기록 저장 커밋 후 health_record 함수를 호출한다. daily는 함수 내부에서 제외한다.
2. A가 같은 건강기록의 predictions와 전체 prediction_contributions를 커밋한 후 prediction 함수를 호출한다. 미진단자의 개인 위협도는 이 시점에 갱신된다.
3. health_record 함수만 붙여도 미진단자 위협도가 생기는 것은 아니다. 아티팩트는 척도·전역 중요도 메타데이터이며 개인 추론과 SHAP을 대신하지 않는다.
4. D 함수 오류로 이미 저장한 건강기록/완료 예측을 실패 처리하지 않는다. 호출 측에서 오류를 기록하고 갱신 재시도 경로를 마련한다. A 예측 done을 D 오류 때문에 failed로 바꾸지 않는다.

이 PR은 C 건강정보 코드와 A 예측/워커 코드를 수정하지 않는다. 각 담당자가 호출을 연결한다. user_monsters만 갱신하고 users·predictions·health_records에는 쓰지 않는다.

## 계산·저장 규칙

- 개인 경로는 기존 personal_threat_score를 재사용한다. signed SHAP 양수만 사용하고 모델 버전별 P95로 0~100을 계산한다. 음수에 절댓값을 적용하지 않는다.
- 진단 경로는 현재 승인된 behavior_weight와 실제 운영 카드 매핑을 함께 적용한다. 현재 흡연 이외의 미확정 숫자는 만들지 않는다.
- 정확히 같은 health_record_id와 artifact.model_version의 done 결과만 읽는다. 더 오래된 입력/작업·pending·다른 버전은 현재 결과를 덮어쓰지 않는다.
- daily 기록은 새로운 예측 입력으로 간주하지 않는다. 호출 측과 추천 측의 최신 기록 선택도 같은 기준으로 맞출 필요가 있다.
- 필요한 지원 factor의 SHAP·척도·weight가 없으면 그 몬스터는 갱신하지 않는다. 처음부터 값이 없으면 도감의 기본 unmeasured가 유지된다. 이전 성공값이 있는 경우 그 값과 last_health_record_id/last_prediction_id는 보존되며 현재 입력으로 계산된 것처럼 출처를 바꾸지 않는다. 화면은 새 예측 완료 전에는 마지막 성공 결과임을 표시해야 한다.
- 모델 metadata의 experimental 표시를 제거하거나 trained로 바꾸지 않는다. 화면의 실험 모델 안내는 기존 CHLG-01 model_experimental 계약을 유지한다.
- 위협도만 갱신하며 XP·공략 점수·active 공략 대상은 바꾸지 않는다.
- 기존 sealed·sealed_at·seal_count를 보존한다. 이후 위협도가 상승하면 reawakened_at에 시각을 남긴다. 봉인 기록을 회수하지 않는다.
- 처음부터 0이면 not_contributing, 과거 양수였던 값이 0이 되면 resolved이며 최초 resolved_at을 보존한다.

## 연결 전에 합의할 D 정책

1. **복수 factor 대표값: 최댓값 제안.** 같은 질환×factor별 점수를 계산한 후 한 몬스터의 여러 요인·두 질환 중 가장 큰 점수를 대표값으로 사용한다. 합산이나 평균으로 임의 결합하지 않는다. 현재 코드·테스트가 이 안을 사용하므로 A·D 확인 후 연결한다.
2. **외형 구간:** 기존 기획서 v12 4.4의 40·70을 경계 중복 없이 stable=1~39, caution=40~69, rage=70~100으로 처리했다. 0과 미평가는 별도 상태다. 이는 게임 외형 기준이며 질환 확률의 낮음·주의·높음 경계와는 별개다.
3. **스파이크:** 공복혈당/HbA1c를 0~100으로 바꾸는 수식·누락 정책이 없어 measured_scorer를 기본 제공하지 않는다. 값이 있어도 승인 수식이 없으면 임의 점수를 만들지 않는다. 승인 후 ImpactService에 scorer를 주입해 연결한다.
4. **진단자 조건:** BMI·허리·걷기·근력·좌식·알코올의 미확정 조건은 보류한다. 실제 입력 상태와 승인 카드에 연결되는 조건표가 먼저 필요하다. 미진단자의 모델 SHAP 경로까지 이 이유로 일괄 차단하지 않는다.
5. **새 봉인:** 28일 종료 자체를 봉인으로 판정하지 않는다. 현재 1단계 habit_established=NULL 및 예정 기회 수행률 정책에 맞는 새 봉인 조건이 확정되지 않았으므로 sealed 반환은 빈 목록이다. 기존 봉인 보존·상승 기록과 새 봉인 지급은 분리한다.

## 팀 의견 및 우선순위

- P0 A: 예측 API 3개(접수·상태/결과·기여도)와 실제 모델/전처리/SHAP 연결. 최신 AGENTS.md에서 A가 예측 테이블을 맡는다.
- P0 D: 이 갱신 함수를 연결하고 도감→공략 대상→추천 통합 확인.
- P0 모델 자료: 두 선택 모델의 실제 가중치, 동일 전처리·feature 순서, 버전 정보와 질환별 메타데이터를 함께 확인한다. metadata artifact만으로 실제 확률/개인 SHAP을 계산할 수 없다. 예측에 저장할 버전은 합쳐진 serving artifact.model_version이며 원본 두 질환 버전은 별도로 추적한다.
- 예측 방식은 현재 202 + prediction_id/job_id + 상태 폴링 계약을 유지하는 안을 권한다. compose에는 Redis가 이미 있다. 1단계는 단일 worker와 기존 상태 3개로 범위를 제한하되 같은 작업 재처리 방지·실패/timeout·DB-큐 유실 복구는 생략하지 않는다. FastAPI BackgroundTasks나 연출 대기를 worker 구현으로 설명하지 않는다.
- 동기 전환은 실제 추론/SHAP 소요 시간 확인과 AGENTS.md·원본 API/요구사항·실패 계약 변경을 함께 합의한 경우의 대안이다. 현재 Draft에서 동기 전환을 구현하지 않았다.
- 프론트는 같은 저장소 frontend/로 두는 안을 권한다. HTML 시안 재공유 후 스택과 담당을 합의한다. 제안 분담은 A 예측·백엔드 연결, D 도감/챌린지 문구·정책·통합 확인, 병주님 프론트 구현·배포다. 타 담당자의 인수 동의 전 확정 분담으로 표시하지 않는다.
- 화면 v3의 실제 파일은 열람하지 못했다. 추천 최대 2개 선택은 최초 투입에만 맞으며 2주차에는 서버의 남은 슬롯·추가 투입 한도에 맞춰 선택 수를 제한해야 한다. 인증 버튼 클릭 자체가 아니라 서버가 인정한 완료 결과로 XP·공략 점수·보상 안내를 갱신한다.
- 5종 도감 중 현재 시드가 4종이며 소디는 보류다. 위협도와 공략 점수를 별도로 표시한다. 28일 종료는 기간 종료·수행률 표시이며 습관 졸업이나 자동 봉인이 아니다.

## 검증

- Python 3.13.15에서 새 테스트 19개 통과.
- app 전체 250개 통과. DB는 전용 SQLite in-memory 테스트 설정을 주입했다.
- 저장소 code_fommatting.sh 통과(Ruff lint·format), check_mypy.sh 통과(120개 소스). 실행 환경의 누락 pandas-stubs는 로컬 환경에 설치했으며 pyproject/uv.lock을 변경하지 않았다.
- MySQL 전용 테스트 서버를 시작하려 했으나 이 실행 환경이 UNIX 소켓 생성을 허용하지 않아 실행하지 못했다. MySQL locking·FK·동시 요청 검증과 기본 run_test.sh의 MySQL 실행은 팀 CI에서 확인해야 한다. SQLite 통과를 MySQL 통과로 해석하지 않는다.
- 실제 모델 파일과 API/worker가 아직 연결되지 않아 smoke 10단계 재검증은 수행하지 않았다. 예측 확률·위협도·보상을 시연용 임의 수치로 채우지 않았다.

## 적용·PR

추가 파일은 impacts.py, test_impacts.py, 이 문서 3개다. 스키마·마이그레이션·원본 시트 사본·현재 모델/마스터 값은 변경하지 않는다.

Draft에서 정책 항목을 확인한 뒤 MySQL CI를 통과시키고, A/C 호출 연결 PR과 전체 smoke를 확인한다. 이 함수가 있는 것만으로 예측 API와 worker가 완성되거나 모든 추천 차단이 풀리는 것은 아니다.
