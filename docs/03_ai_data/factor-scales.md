# KNHANES 선택 모델의 factor별 위협도 기준값

기준일: 2026-10-01 KST. 선택 모델의 실제 학습 결과에서 계산한 실험 기준값이며, 배포 승인·임상 판단 기준은 아니다. 계산 원본과 개인 단위 SHAP은 `.gitignore`된 `data/experiment-2024-final-full/` 안에 보관한다.

## 계산 기준

- 당뇨 model version: `knhanes-ix-diabetes-base_sitting-s42`; 고혈압: `knhanes-ix-hypertension-base_sodium-s42`.
- 학습·기준집단은 각각 2022 eligible 성인 전체다. 당뇨 n=4,418(양성 149), 고혈압 n=3,697(양성 373). 2023 validation이나 2024 비교 자료는 P95 산출에 쓰지 않았다.
- `mean_abs_grouped_shap`은 2022 전체 기준집단의 grouped signed SHAP 절댓값 평균이다. SHAP은 예측 유병확률 공간이다.
- model-version 고정 `global_importance_max`: 당뇨 `0.0145940362783` (`age`), 고혈압 `0.0299582109239` (`age`). `global normalized score = importance / disease max × 100`.
- `positive_shap_p95`는 각 요인의 양수 grouped SHAP만 모아 계산한 P95다. `positive_n`은 이 양수 행 수다.
- 현 `prediction_contributions.contribution`은 `DECIMAL(8,5)`다. `threat_eligible=true` 규칙은 P95가 `0.00001` 이상이고 양수 표본이 400개 이상인 것(양수 분포 상위 5%에 기대 관측치 20개 이상)이다. 저장 정밀도·꼬리 표본 지지 기준이며 임상 임계값이 아니다.
- 판정: 아래 24개 질환×factor 조합은 모두 `threat_eligible=true`. 최소 P95는 당뇨 `strength_activity_low`의 0.00098525(5자리 반올림 0.00099), 최소 양수 표본은 당뇨 `smoking_current`의 707/4,418이다. 즉 P95 기준 최소 98개 저장 단위이고, P95 상위 꼬리 기대 표본은 최소 약 35개다.

## 당뇨 — core + `sedentary_time_high`

| factor_key | mean\|SHAP\| 원값 | global normalized score | rank | positive_shap_p95 | positive_n / reference_n | threat_eligible |
|---|---:|---:|---:|---:|---:|---|
| age | 0.01459404 | 100.00 | 1 | 0.02868844 | 2,437 / 4,418 | true |
| family_history_dm | 0.00970070 | 66.47 | 2 | 0.04031075 | 1,016 / 4,418 | true |
| waist_high | 0.00925352 | 63.41 | 3 | 0.04061248 | 1,243 / 4,418 | true |
| bmi_high | 0.00737227 | 50.52 | 4 | 0.03679990 | 1,457 / 4,418 | true |
| physical_activity_low | 0.00313945 | 21.51 | 5 | 0.01340316 | 1,743 / 4,418 | true |
| sedentary_time_high | 0.00308196 | 21.12 | 6 | 0.01602607 | 1,415 / 4,418 | true |
| alcohol_amount | 0.00270651 | 18.55 | 7 | 0.00919861 | 2,402 / 4,418 | true |
| sex | 0.00234102 | 16.04 | 8 | 0.00703614 | 1,940 / 4,418 | true |
| smoking_current | 0.00190359 | 13.04 | 9 | 0.01288859 | 707 / 4,418 | true |
| alcohol_frequency | 0.00161927 | 11.10 | 10 | 0.00785815 | 1,654 / 4,418 | true |
| family_history_htn | 0.00142038 | 9.73 | 11 | 0.00259738 | 2,523 / 4,418 | true |
| strength_activity_low | 0.00058345 | 4.00 | 12 | 0.00098525 | 3,231 / 4,418 | true |

## 고혈압 — core + `sodium_behavior` proxy

| factor_key | mean\|SHAP\| 원값 | global normalized score | rank | positive_shap_p95 | positive_n / reference_n | threat_eligible |
|---|---:|---:|---:|---:|---:|---|
| age | 0.02995821 | 100.00 | 1 | 0.06972658 | 1,952 / 3,697 | true |
| waist_high | 0.01872522 | 62.50 | 2 | 0.05381498 | 1,411 / 3,697 | true |
| sex | 0.01343938 | 44.86 | 3 | 0.02497764 | 1,516 / 3,697 | true |
| bmi_high | 0.01292694 | 43.15 | 4 | 0.04093382 | 1,377 / 3,697 | true |
| alcohol_frequency | 0.00895319 | 29.89 | 5 | 0.07276599 | 1,267 / 3,697 | true |
| alcohol_amount | 0.00811129 | 27.08 | 6 | 0.02144051 | 1,741 / 3,697 | true |
| physical_activity_low | 0.00668347 | 22.31 | 7 | 0.02121899 | 1,803 / 3,697 | true |
| sodium_behavior | 0.00560963 | 18.72 | 8 | 0.03764245 | 1,004 / 3,697 | true |
| smoking_current | 0.00276446 | 9.23 | 9 | 0.01686260 | 810 / 3,697 | true |
| family_history_htn | 0.00232091 | 7.75 | 10 | 0.00756848 | 1,435 / 3,697 | true |
| family_history_dm | 0.00183012 | 6.11 | 11 | 0.00443919 | 2,323 / 3,697 | true |
| strength_activity_low | 0.00173842 | 5.80 | 12 | 0.01112578 | 1,958 / 3,697 | true |

## `behavior_weight` 및 외식 빈도 판단

2026-10-01 Slack에서 A는 MVP를 이진 weight로 두는 안에 찬성했다. 따라서 진단자 식은 `normalized_score × behavior_weight`, weight는 사용자별 0/1이다. 유효 입력이 승인된 `risk_condition`을 충족하고 그 사용자가 실제로 할 수 있는 매핑 챌린지가 있으면 1, 유효 입력이 비대상이거나 매핑 챌린지가 없으면 0이다. 누락·모름은 건강한 행동으로 처리하지 않고 미평가로 두며 추천하지 않는다. age·sex·가족력처럼 행동으로 바꾸기 어려운 factor는 `threat_eligible=true`여도 챌린지 weight 대상이 아니다. [D 조건 초안과 A의 binary weight 의견](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790827443192909?thread_ts=1790827443.192909)

D 초안과 Slack 답변에서 현재 확정할 수 있는 적용조건과 남은 기준은 다음과 같다. 이 조건표가 실제 서비스 입력을 반영하기 전까지 weight는 실험/초안 상태다.

| factor | `behavior_weight=1` 조건 초안 | 상태 |
|---|---|---|
| age, sex, family history | 해당 없음(수정 가능한 행동 챌린지 없음) → 추천 weight 0 | 비행동 요인 |
| smoking_current | `sm_presnt=1`(현재 흡연). 결측은 미평가 | D·A 동의; 과거 흡연 전용 챌린지는 MVP 제외 |
| alcohol_frequency | `BD1_11=2..6` 최근 1년 음주; 1은 비음주로 제외, 8/미응답은 미평가 | 범주·기간 답변 반영; 챌린지와 cutoff 최종표는 D 확인 필요 |
| alcohol_amount | 최근 1년 음주자(`BD1_11=2..6`)의 유효 `BD2_1=1..5` | 음주 상황에서 적용하는 초안; 양별 제한은 D 결정 대기 |
| bmi_high, waist_high | 기준 이상 | 수치 cutoff 미정 |
| physical_activity_low | 걷기 일수가 승인 기준 미만 | 수치 cutoff와 걷기 시간 병행 여부 미정 |
| strength_activity_low | 근력 일수가 승인 기준 미만 | 수치 cutoff 미정; 모델 변환은 0~5 |
| sedentary_time_high | `BE8_1×60+BE8_2`가 승인 분/일 기준 이상 | 수치 cutoff 미정 |
| sodium_behavior | 자동 추천 적용 보류 | 범주별 model SHAP 부호가 혼합; 단조 risk condition 없음 |
| vegetable_intake_low | 해당 없음 | 제품 입력 미확정·첫 모델 미포함 |

따라서 현재 **척도**는 binary에 합의됐지만, BMI·허리·활동·좌식 cutoff와 알코올/챌린지 조합에 대한 **실제 user별 weight 출력**은 D의 조건표 승인 뒤 계산해야 한다.

조건 적용 전 2023 validation 256명 비교에서 `behavior_weight=1`일 때 global 점수가 personal P95 점수 이상인 비율은 선택 좌식 factor 83.6%, sodium factor 92.6%였다. 이 1.0 비교는 최대값일 뿐 승인된 weight를 의미하지 않는다. 행동 조건을 필터링하고 같은 사용자에서 분포를 다시 확인하지 않으면 global 경로가 더 큰 점수를 자주 낼 수 있다.

`sodium_behavior` 산출은 `L_OUT_FQ` 코드 1~7 외식 빈도를 범주값 그대로 사용해 SHAP을 계산하는 것이다. 나트륨 섭취량, mg/g, 또는 식단 속 나트륨으로 변환하지 않는다. 팀 범위상 고혈압 모델에만 둔다. 2024 비교에서 core+sodium은 base보다 AUROC +0.001400, AP +0.005599, Brier −0.000101이었으나, 2023 validation에서는 AUROC −0.00320, AP −0.00321로 악화됐다. 2024는 변형 선택에 사용했으므로 독립적인 최종 검증이 아니다.

방향도 단순하지 않다. 2023 validation SHAP 256명에서 `L_OUT_FQ` 코드 1~3 평균 signed SHAP은 −0.003090, 코드 4는 −0.010836, 코드 5는 +0.000695, 코드 6~7은 +0.006959였다. 코드가 작을수록 외식이 잦지만, 더 잦은 구간이 이 모델에서 양의 기여를 보인다는 일관된 관계는 없다. 따라서 외식 빈도 감소를 전제로 한 챌린지와 `behavior_weight=1` 조건은 지금 고정하지 않는다. `L_OUT_FQ`는 고혈압의 실험 X 후보로 남기고, D가 코드 구간·챌린지 의미를 검토한 뒤에만 추천 weight를 산출한다.

이 문서는 선택된 실험 model version의 scale 기록이다. 2024 비교에 feature 선택을 맞췄으므로, 이를 배포 성능이나 미래 발병 위험으로 표현하지 않는다. 새 모델 버전에는 해당 버전의 전체 train reference에서 scale을 다시 계산한다.
