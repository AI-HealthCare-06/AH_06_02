# factor_key ↔ 챌린지 키 대조표

> 상태: v0 원본을 최신 계약에 대조한 검토본. 자동 추천 승인 표가 아닙니다.
> 검토일: 2026-10-06. 실제 모델의 질환별 지원 여부·artifact metadata·사용자 적용 조건은 별도로 확인합니다.

근거: REQ-CHLG-001·007·012, `ai_worker/model_contract.py`, `table-spec.md`.

## 계약의 factor_key

현재 FEATURE_FACTOR는 입력 이름 15개를 고유 factor_key 14개에 연결합니다. 채소 후보를 제외하면 13개입니다. 사전에 문자열이 있는 것과 최종 모델 채택은 다릅니다.

| factor_key | 연결된 v0 챌린지 키 | 상태 |
|---|---|---|
| `age` | — | 수정 불가·추천 연결 없음 |
| `alcohol_amount` | `CH_ONE_LESS_GLASS` · `CH_WATER_BETWEEN` | 문자열 일치 확인·운영 조건 승인 별도 |
| `alcohol_frequency` | `CH_NO_DRINK_TODAY` | 문자열 일치 확인·운영 조건 승인 별도 |
| `bmi_high` | — | 연결 카드 없음 |
| `family_history_dm` | — | 수정 불가·추천 연결 없음 |
| `family_history_htn` | — | 수정 불가·추천 연결 없음 |
| `physical_activity_low` | `CH_WALK_AFTER_MEAL` · `CH_STAIRS` · `CH_WALK_ONE_STOP` | 문자열 일치 확인·운영 조건 승인 별도 |
| `sedentary_time_high` | `CH_STAND_HOURLY` | 문자열 일치 확인·운영 조건 승인 별도 |
| `sex` | — | 수정 불가·추천 연결 없음 |
| `smoking_current` | `CH_NO_SMOKE_TODAY` · `CH_DELAY_5MIN` · `CH_COUNT_DOWN` | 문자열 일치 확인·운영 조건 승인 별도 |
| `sodium_behavior` | `CH_LEAVE_SOUP` · `CH_NO_EATING_OUT` · `CH_CHECK_LABEL` · `CH_HOME_MEAL` | 고혈압 실험 요인·외식 대리 지표·추천 조건 승인 대기 |
| `strength_activity_low` | `CH_STRENGTH_10` | 문자열 일치 확인·운영 조건 승인 별도 |
| `vegetable_intake_low` | — | 최종 X 미채택 후보·운영 연결 없음 |
| `waist_high` | — | 연결 카드 없음 |

## 19개 키별 대조

캐릭터는 v0의 group 값입니다. 특히 스파이크 공유 연결을 확정한 값이 아닙니다. is_enabled는 v0 저장값을 표시하며 현재 서비스 운영 승인 상태를 뜻하지 않습니다.

| 키 | factor_key | v0 캐릭터 | v0 활성 | 1단계 확인 사항 |
|---|---|---|---|---|
| `CH_WALK_AFTER_MEAL` | `physical_activity_low` | 비세라 | True | 개인화 조합·식사 슬롯·시작일 지난 슬롯 제외 |
| `CH_STAND_HOURLY` | `sedentary_time_high` | 비세라 | True | 3분 × 1/2/3회·예정 독립 회차 |
| `CH_STAIRS` | `physical_activity_low` | 비세라 | True | 안전 확인·완료 행동 구체화 |
| `CH_STRENGTH_10` | `strength_activity_low` | 비세라 | True | 안전 확인·예정 운동일 확인 |
| `CH_WALK_ONE_STOP` | `physical_activity_low` | 비세라 | True | 예정 이용일 확인 시 반복 실천 후보; event 표기와의 정합화 필요 |
| `CH_LEAVE_SOUP` | `sodium_behavior` | 소디 | True | supporting 변경 검토·예정 식사/슬롯 확인 |
| `CH_NO_EATING_OUT` | `sodium_behavior` | 소디 | True | 하루 전체 행동·종료 후 확인 규칙 |
| `CH_CHECK_LABEL` | `sodium_behavior` | 소디 | True | 구매 발생형은 제외; 예정 관찰/준비로 바꾸려면 승인 필요 |
| `CH_HOME_MEAL` | `sodium_behavior` | 소디 | True | 예정 식사 슬롯·완료 행동 확인 |
| `CH_NO_DRINK_TODAY` | `alcohol_frequency` | 알데 | True | 하루 전체 행동·현재 음주 사용자·종료 후 확인 |
| `CH_ONE_LESS_GLASS` | `alcohol_amount` | 알데 | True | 음주 상황 발생형·1단계 추천 제외 |
| `CH_WATER_BETWEEN` | `alcohol_amount` | 알데 | True | 음주 상황 발생형·1단계 추천 제외 |
| `CH_NO_SMOKE_TODAY` | `smoking_current` | 코티니 | True | 하루 전체 행동·현재 흡연 사용자·종료 후 확인 |
| `CH_DELAY_5MIN` | `smoking_current` | 코티니 | True | 욕구 발생형·1단계 추천 제외·supporting 변경 검토 |
| `CH_COUNT_DOWN` | `smoking_current` | 코티니 | True | 관찰형·0 기록과 미입력 구분; 완료 규칙 미승인 |
| `CH_VEGGIE_FIRST` | NULL | 스파이크 | False | 비활성·factor_key 미정; 재활성화 금지 |
| `CH_SLOW_EAT_20` | NULL | 스파이크 | False | 비활성·factor_key 미정; 재활성화 금지 |
| `CH_WATER_8` | NULL | 보너스 | True | 최종 활성값·잔 용량·MVP 범위 확인 필요 |
| `CH_SLEEP_7H` | NULL | 보너스 | True | 최신 모델 문서상 MVP 보류·최종 활성값·단위 확인 필요 |

## 등록·활성·추천 가능 수

| 캐릭터 | v0 등록 | v0 활성 | 1단계 제외 사항 | 운영 추천 가능한 수 |
|---|---:|---:|---|---|
| 비세라 | 5 | 5 | 안전·예정 기회·완료 조건 검증 필요 | 미확정 |
| 소디 | 4 | 4 | 구매 발생형 제외·자동 추천 적용 보류 | 미확정 |
| 알데 | 3 | 3 | 음주 상황 발생형 2개 제외 후 기존 후보 1개 | 승인 전 미확정 |
| 코티니 | 3 | 3 | 욕구 발생형 제외·관찰 완료 규칙 미확정 | 미확정 |
| 스파이크 | 2 | 0 | factor_key 미확정으로 비활성 유지 | 0 |
| 보너스 | 2 | 2 | 물·수면의 MVP 범위와 실제 v1 확인 필요 | 미확정 |

등록·활성 수와 추천 가능 수는 다르다. 후보 문서 일부에 등장하는 키 개수를 전체 마스터나 운영 추천 가능 수로 사용하지 않는다.

챗봇 후보 v2의 일부 연결표는 전체 마스터가 아닙니다. 등록 수와 운영 추천 가능 수를 그 표의 행 수로 대신하지 않습니다. 보강 후보 4개와 비세라 데모 방향은 [challenge-candidates.md](challenge-candidates.md)에 정리합니다.

## 최신 모델 상태

2024 비교 평가는 main의 B 실험 문서에 반영되어 있습니다. 입력 선택에 사용했으므로 독립 holdout 평가라고 부르지 않습니다. sodium_behavior는 고혈압 실험에 포함됐지만 나트륨 실측값이 아닙니다. 서비스의 소디는 고혈압 대상 기존 설계를 유지하며, 모델·위협도·자동 추천 적용은 추가 검증 후 결정하는 후보 상태입니다. 행동 cutoff·자동 weight와 소디 조절 범위는 보류합니다. 실험상 입력 선택과 서비스 운영 승인을 구분합니다. vegetable_intake_low는 사전에 있으나 final X에 미채택입니다. 배포 artifact는 별도 의존성입니다.

BMI·허리·진단자 behavior_weight의 숫자 조건은 과거 초안에 있어도 팀 승인 전 런타임 규칙으로 전환하지 않습니다.

대조 원본: 사용자 제공 challenge_master_v0_reviewed.csv 및 D_mapping_table_v1.docx. 최신 계약은 저장소 ai_worker/model_contract.py입니다. 과거 초안 전체를 저장소에 추가하지 않았습니다.

시드 입력 CSV는 [challenge-master.csv](challenge-master.csv), 3단계 준비 상태와 세 키 난이도는 [challenge-candidates.md](challenge-candidates.md)를 확인합니다.
