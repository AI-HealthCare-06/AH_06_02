# KNHANES 입력 선택 및 2024 비교 평가

상태: 2026-10-01, 2026-10-11 재적합·2019 평가 반영. 목적은 당뇨·고혈압의 입력 후보를 비교하고, 팀에서 요청한 2024 평가로 외식 빈도 기반 `sodium_behavior`의 적용 여부를 정하는 것이다. 결과는 실험용이며 성능 최적화·임상 판단·배포 인증이 아니다.

## 설계

지금 구조는 다음과 같다. 학습은 2022+2023 eligible 행이다. 입력 조합(base·sodium·sitting·sodium_sitting·vegetable) 선택은 2023 validation 으로 했고, 과거에는 2024 비교 평가도 선택에 사용했다(아래 2024 비교 절). 운영 임계값은 학습 연도 안 5-fold 층화 교차검증의 out-of-fold 예측에서 재현율 0.70 지점으로 정한다. 평가는 2024 와 2019 다. 질환별로 미진단·미복약 성인만 eligibility에 포함하고 유효 y가 없는 행은 제외했다. RandomForest(200 trees, min leaf 10, max depth 10), train-only median/mode imputation과 one-hot encoding, seed 42·43·44를 썼다. 2024 는 입력 선택에 쓰였으므로 선택 과정까지 포함한 독립 평가는 아니고, 2019 는 어떤 단계에도 쓰이지 않은 독립 평가다. 서빙 아티팩트는 seed 42 모델이다.

| variant | feature |
|---|---|
| base | model.md의 12개 core feature |
| sodium | base + `dining_out_freq` (`sodium_behavior`) |
| sitting | base + `sitting_minutes` (`sedentary_time_high`) |
| sodium_sitting | base + 두 후보 |
| vegetable | base + `vegetable_frequency` (`vegetable_intake_low`, LS_VEG2) |

초기 30회 탐색의 개인 위협도 P95와 전역 중요도는 seed 고정 256명 reference를 쓴다. 이는 척도·factor 분리 탐색치다. 최종 입력 선택 뒤 seed 42 모델의 전체 eligible 2022 training 행에서 positive-SHAP P95와 전역 중요도를 다시 계산했고 결과는 ignored `data/experiment-2024-final-full/`에 저장했다. 개인 기여도와 `global normalized_score × candidate behavior_weight`는 같은 2023 validation 사용자 SHAP sample에서 비교했다.

## 3-seed 평균 validation 결과

| 질환 | variant | AUROC | Average precision | Brier |
|---|---|---:|---:|---:|
| 당뇨 | base | 0.73162 | 0.10164 | 0.03752 |
| 당뇨 | sodium | 0.73687 | 0.10469 | 0.03747 |
| 당뇨 | sitting | 0.73253 | 0.10404 | 0.03750 |
| 당뇨 | sodium_sitting | 0.73805 | 0.10607 | 0.03745 |
| 고혈압 | base | 0.71807 | 0.18723 | 0.07958 |
| 고혈압 | sodium | 0.71487 | 0.18402 | 0.07964 |
| 고혈압 | sitting | 0.71789 | 0.18931 | 0.07951 |
| 고혈압 | sodium_sitting | 0.71652 | 0.18627 | 0.07956 |
| 당뇨 | vegetable | 0.73144 | 0.10403 | 0.03750 |
| 고혈압 | vegetable | 0.71692 | 0.17994 | 0.07966 |

각 행은 seed 42·43·44의 평균이다. 각 변형은 당뇨 validation n=4,838·양성 194, 고혈압 n=4,143·양성 381로 평가됐다. 보고서 `data/experiment-final/report.json`은 `.gitignore` 아래 로컬에만 둔다. 개인 단위 특징·행 SHAP을 Git이나 Slack에 올리지 않는다.

## 2024 비교 평가 (3-seed 평균)

| 질환 | variant | AUROC | Average precision | Brier |
|---|---|---:|---:|---:|
| 당뇨 | base | 0.774786 | 0.107245 | 0.037353 |
| 당뇨 | sodium | 0.776758 | 0.107129 | 0.037379 |
| 당뇨 | sitting | 0.772550 | 0.109683 | 0.037328 |
| 당뇨 | sodium_sitting | 0.777124 | 0.109526 | 0.037362 |
| 고혈압 | base | 0.724375 | 0.218040 | 0.092610 |
| 고혈압 | sodium | 0.725775 | 0.223639 | 0.092509 |
| 고혈압 | sitting | 0.723968 | 0.220122 | 0.092610 |
| 고혈압 | sodium_sitting | 0.722463 | 0.222494 | 0.092678 |

2024 평가 표본은 당뇨 n=4,853(양성 196), 고혈압 n=4,226(양성 467)이다. 희귀 양성 라벨을 고려해 후보 판단의 우선 지표는 average precision으로 두고 AUROC·Brier도 함께 확인했다. team scope상 `sodium_behavior`는 고혈압에만 고려했다. 이에 첫 모델의 입력을 당뇨 core+sitting으로 선택했다(AP +0.002438, Brier −0.000025, AUROC −0.002236 대 base), 고혈압 core+sodium으로 선택했다(AP +0.005599, AUROC +0.001400, Brier −0.000101 대 base). 당뇨의 sodium·sodium_sitting 성능이 더 높아 보이는 일부 지표가 있어도 sodium의 당뇨 확장은 합의 범위 밖이다.

## 2022+2023 재적합과 2024 평가 (2026-10-11)

선택한 두 입력 변형(당뇨 core+sitting, 고혈압 core+sodium)을 2022+2023 eligible 행으로 다시 학습했다. 2023 은 이번에 학습 연도에 들어가므로 별도 validation 지표는 학습에 쓴 행의 점수(`in_training: true`)라 성능 근거로 쓰지 않는다. 대신 학습 연도 안에서 5-fold 층화 교차검증으로 어느 fold 에도 학습되지 않은 예측(out-of-fold)을 만들고, 그 예측에서 재현율 0.70 운영 임계값을 정했다(`operating_point_source: out_of_fold`). 2024 는 학습·임계값·P95 어디에도 쓰지 않고 마지막에 한 번만 평가했다. seed 42, SHAP reference 는 학습 행 전체(`--reference-size 0`)다.

| 질환·선택 모델 | 학습 n (2022+2023) | 학습 양성 | 임계값 출처 | out-of-fold AUROC / AP / Brier | 운영 임계값 |
|---|---:|---:|---|---|---:|
| 당뇨 · core+sitting | 9,256 | 343 (이전 149) | 5-fold | 0.747958 / 0.092300 / 0.034678 | 0.040449 |
| 고혈압 · core+sodium | 7,840 | 754 (이전 373) | 5-fold | 0.731691 / 0.200345 / 0.081939 | 0.108273 |

| 질환·선택 모델 | 2024 n | 2024 AUROC / AP / Brier | 2024 재현율 / 특이도 | 이전(2022 단독) 2024 AUROC / AP / Brier | 이전 재현율 / 특이도 |
|---|---:|---|---|---|---|
| 당뇨 · core+sitting | 4,853 (양성 196) | 0.779303 / 0.108294 / 0.037270 | 0.7449 / 0.6575 | 0.774021 / 0.112496 / 0.037272 | 0.7755 / 0.6416 |
| 고혈압 · core+sodium | 4,226 (양성 467) | 0.730458 / 0.225532 / 0.092470 | 0.7045 / 0.6462 | 0.726962 / 0.222261 / 0.092491 | 0.6852 / 0.6385 |

2024 는 이번 학습과 임계값 결정에 쓰지 않았다. 다만 입력 변형(sitting·sodium) 자체는 앞선 2024 비교로 골랐으므로, 이 2024 성적도 선택 과정까지 포함한 완전한 독립 추정은 아니다. 실험 산출물 표시(`experiment_only_not_deployable`)는 그대로 둔다.

P95 가 바뀌면 같은 개인 SHAP 이라도 위협도 산출 기준이 바뀐다. 행동 챌린지와 연결된 요인 중 변화가 큰 것은 당뇨 `strength_activity_low` +89.5%, `waist_high` +38.8%, `alcohol_frequency` +35.2%, `physical_activity_low` -34.1%, 고혈압 `strength_activity_low` -76.5%, `sodium_behavior` -59.8%, `smoking_current` -56.6%, `bmi_high` -33.3%다. 진단자 경로가 쓰는 전역 normalized score 도 바뀌어 `smoking_current` 는 당뇨 13.04 → 9.41, 고혈압 9.23 → 3.28 이다. 전체 표는 [factor별 척도표](factor-scales.md)에 있고 24개 조합 모두 `threat_eligible=true` 다.

재실행 환경의 numpy 는 2.5.4 로 기존 기록(2.5.3)과 다르다. 2022 단독 설정을 같은 명령으로 다시 돌려 비교했을 때 영향은 운영 임계값 1 ULP(0.03561978214592075 → …076) 뿐이었고 재현율·특이도·나머지 지표와 P95 표는 모두 같았다.

결과 원본은 ignored `data/experiment-refit/` 아래에만 둔다. 두 명령이 같은 출력 폴더를 쓰므로 질환별 report 는 `report-diabetes.json`·`report-hypertension.json` 으로 따로 보관했다.

## seed 변동폭 (seed 42·43·44, 2026-10-11)

학습 연도·입력 조합·SHAP reference 는 위 재적합과 같고 seed 만 바꿨다. 값은 최소 / 중앙 / 최대다.

| 실행 | 교차검증 AP | 평가 AP | 평가 AUROC |
|---|---|---|---|
| 당뇨 · core+sitting · 2024 평가 | 0.0893 / 0.0923 / 0.1025 | 0.1083 / 0.1110 / 0.1137 | 0.7793 / 0.7807 / 0.7809 |
| 당뇨 · core+sitting · 2019 평가 | 0.0893 / 0.0923 / 0.1025 | 0.1513 / 0.1567 / 0.1572 | 0.7802 / 0.7808 / 0.7816 |
| 고혈압 · core+sodium · 2024 평가 | 0.2003 / 0.2049 / 0.2102 | 0.2230 / 0.2255 / 0.2277 | 0.7303 / 0.7305 / 0.7325 |

당뇨 두 행은 같은 모델을 다른 연도로 평가한 것이라 교차검증 AP 가 같다. 가장 큰 폭은 당뇨 교차검증 AP 의 0.0132 다. 학습 양성 343명을 5-fold 로 나눠 계산하는 값이라 seed 에 민감하다. 평가 AUROC 의 seed 간 폭은 모두 0.003 이하다. 운영 임계값이 seed 마다 학습 연도 안에서 다시 정해지므로 당뇨 2024 재현율은 0.7449\~0.7908 로 움직인다. 9개 run 모두 `operating_point_source: out_of_fold` 이고 `threat_eligible=false` 인 factor 는 없다.

위 표는 seed 세 개의 최소 / 중앙 / 최대다. 서빙 아티팩트는 seed 42 모델이므로, 서비스가 실제로 쓰는 값은 중앙값이 아니라 seed 42 의 값이다. seed 42 의 평가 AUROC 는 당뇨 2024 0.7793, 당뇨 2019 0.7816, 고혈압 2024 0.7305 다. 숫자를 인용할 때 어느 기준인지 밝힌다.

## 평가셋별 기준선과 2019 독립 평가

AP 는 평가셋의 양성률이 무작위 예측의 기준선이 되므로 평가셋마다 기준이 다르다. 양성률과 기준선 대비 배수를 함께 적는다(배수는 최소 / 중앙 / 최대).

| 평가셋 | n (양성) | 양성률 = 기준선 AP | 평가 AP ÷ 기준선 | 평가 AUROC 중앙값 |
|---|---:|---:|---|---:|
| 당뇨 · 2024 | 4,853 (196) | 0.0404 | 2.68 / 2.75 / 2.82 | 0.7807 |
| 당뇨 · 2019 | 5,345 (282) | 0.0528 | 2.87 / 2.97 / 2.98 | 0.7808 |
| 고혈압 · 2024 | 4,226 (467) | 0.1105 | 2.02 / 2.04 / 2.06 | 0.7305 |
| 고혈압 · 2019 | 4,659 (543) | 0.1165 | 1.90 / 1.91 / 1.92 | 0.7225 |

2019 는 입력 조합 선택(2023 validation·과거 2024 비교), 학습(2022+2023), 운영 임계값(학습 연도 안 교차검증), P95 계산 어디에도 쓰지 않은 자료다. 그래서 선택 과정까지 포함한 독립 평가다. 2019 에서 당뇨 판별 성능은 2024 와 비슷했다. 서빙 모델인 seed 42 기준으로 2019 AUROC 0.7816, 2024 0.7793 이고, seed 세 개 중앙값으로는 0.7808 대 0.7807 이다.

여기서 말할 수 있는 것은 쓰지 않은 자료에서도 판별 성능이 유지됐다는 데까지다. 두 값이 비슷하다는 것만으로 2024 를 입력 선택에 쓴 데서 오는 선택 편향이 작다고 확정하지는 않는다. 두 평가셋이 비슷한 난도였을 가능성도 함께 둔다.

고혈압도 2019 로 평가했다. 서빙 모델인 seed 42 기준으로 2019 AUROC 0.7225, AP 0.2221, Brier 0.0975, 운영 임계값(0.108273)에서 재현율 0.6575 · 특이도 0.6630 이다. 같은 모델의 2024 는 AUROC 0.7305 · AP 0.2255 다. 판별 성능이 쓰지 않은 자료에서 조금 낮아졌지만 같은 수준으로 유지됐다. 이 run 의 seed 42 모델은 학습 행·교차검증 지표·운영 임계값이 `data/experiment-refit` 서빙 모델과 같아서, 서비스가 쓰는 모델을 그대로 평가한 값이다.

예전에는 2019 의 `HE_HP` 에 코드 4 가 없어 양성이 0 이 된다고 보고 고혈압 2019 평가를 하지 않았다. 아래 대조에서 보듯 제8기는 코드 체계가 달라 생긴 일이었다.

학습 자료를 약 두 배로 늘렸지만 2024 지표는 거의 그대로였다. 이번 변경으로 얻은 것은 성능이 아니라 평가 구조다.

2019 를 넣어 canonical 을 다시 만들었을 때 2022\~2024 행 17,262 개는 기존 canonical 과 모든 셀이 같았다(열·행 순서 포함). 전처리는 결정적이다. `knhanes-ix-v3` 로 고혈압 라벨 매핑을 넣은 뒤에도 2022\~2024 행은 v2 와 모든 셀이 같고, 2019 행은 `HE_HP` 열만 바뀐다.

## 제8기(2019) 변수 대조

`HN19_ALL.sav` 와 `HN22~24_ALL.sav` 의 SPSS 메타데이터(변수 설명·값 설명)와 연도별 코드 분포를 비교했다. 개인 단위 값은 밖으로 꺼내지 않고 집계만 봤다.

- 모델이 쓰는 입력·라벨·제외 조건 변수는 2019 에도 모두 있다. 변수 설명 문구만 다르다(예: `L_OUT_FQ` "외식 횟수" → "최근 1년 동안 평균 외식 빈도").
- 입력 변수의 코드 집합은 2019 와 2024 가 같다.
- `HE_DM_HbA1c` 는 두 기 모두 1\~3 이고 코드 3 은 두 해 모두 공복혈당 126 또는 HbA1c 6.5 기준을 전원 충족한다. 당뇨 2019 평가는 그대로 유효하다.
- `HE_HP` 는 코드 체계가 다르다. 성인 실측 혈압 범위로 확인한 정의는 아래와 같다.

| 기수 | 코드 | 혈압 범위 (성인 실측) | 의미 |
|---|---|---|---|
| 제8기 (2019) | 1 · 2 · 3 | <120/80 · 120\~139/80\~89 · ≥140/90 또는 혈압약 | 정상 · 전단계 · 고혈압 |
| 제9기 (2022\~2024) | 1 · 2 · 3 · 4 | <120/80 · 120\~129/<80 · 130\~139/80\~89 · ≥140/90 또는 혈압약 | 정상 · 주의 · 전단계 · 고혈압 |

  제8기 3 은 제9기 4 와 같은 정의다. 제8기 2 는 측정 혈압으로 주의(수축기 <130 이고 이완기 <80)와 전단계로 나눈다. 2019 성인 전단계 1,615 명은 모두 혈압 측정값이 있다. 고혈압 평가 대상(미진단·미복약) 양성률은 2019 11.7%, 2024 11.1% 로 비슷하다.
- `DE1_*` · `DI1_*` 는 제9기에만 코드 9(모름)가 있다. 제외 규칙에는 영향이 없다.
- 2019 성인의 걷기·좌식 문항 결측은 310 명으로 2024(2 명)보다 많고, 좌식 시간 최솟값이 2019 는 1 시간, 제9기는 0 시간이다. 정의 차이는 아니고 평가 표본 수에 영향을 준다.
- 혈압 측정 기기·방법이 두 기에서 같은지는 원시 파일로 확인할 수 없다. 이용지침서 확인이 남아 있다.

결과 원본은 ignored `data/experiment-seeds/` 아래에만 둔다.

## 선택 모델 전체-reference 재계산 (2022 단독 학습, 2026-10-01)

선택한 입력으로 seed 42 모델을 다시 학습하고 2022 eligible training 전체에서 grouped SHAP을 계산했다. background는 같은 2022 training 집단에서 seed 고정 100행이며, P95 분포는 전체 training 평가행 기준이다. 2024는 P95에 사용하지 않았다.

| 질환·선택 모델 | 2022 eligible train n | 선택 요인 | positive-SHAP P95 | 전역 normalized_score (rank) | seed 42의 2024 AUROC / AP / Brier |
|---|---:|---|---:|---:|---|
| 당뇨 · core+sitting | 4,418 | `sedentary_time_high` | 0.016026 (양수 1,415명) | 21.118 (6) | 0.774021 / 0.112496 / 0.037272 |
| 고혈압 · core+sodium | 3,697 | `sodium_behavior` | 0.037642 (양수 1,004명) | 18.725 (8) | 0.726962 / 0.222261 / 0.092491 |

전역 원점수는 해당 요인의 전체 2022 SHAP 평균 절댓값이며, score는 각 질환의 최고 전역 중요도를 100으로 둔 `importance / disease_max × 100`이다. 2024 지표는 feature 선택에 사용한 평가 자료이며 독립 성능 추정치가 아니다. 모델별 모든 factor의 원값·P95·양수 표본 수·`threat_eligible` 판정은 [factor별 척도표](factor-scales.md)에 기록했다. 저장 정밀도와 상위 꼬리 표본 기준을 적용한 결과 선택 모델의 24개 조합은 모두 true다. 개인 SHAP 행은 gitignore된 `data/experiment-2024-final-full/` 아래에만 저장한다.

같은 2023 validation 표본 256명에서 risk condition을 적용하기 전에 탐색 가중치 0.25/0.5/0.75/1.0과 개인 위협도를 비교했다. global 경로가 개인 점수 이상인 비율은 좌식 71.9%/76.6%/79.7%/83.6%, sodium 대리요인 85.9%/89.8%/92.2%/92.6%였다. 이 가중치는 비교 실험치이며 팀에서 합의한 binary MVP 값을 대체하지 않는다. D의 실제 행동 조건이 승인되면 그 조건으로 동일 사용자 분포를 다시 집계한다.

## 좌식 factor 및 척도 확인

각 seed에서 sitting model의 grouped SHAP을 `sedentary_time_high`에 따로 보존하고 `physical_activity_low`에 합치지 않았다.

- 당뇨 좌식 전역 normalized score는 18.40–20.67(순위 5–6), 2022 train sample의 positive-SHAP P95는 0.01024–0.01240이다. 고혈압은 score 8.06–8.93(순위 8–10), P95 0.01092–0.01147이다. 3 seed 모두 reference 256명에서 양의 SHAP 관측이 나왔다.
- sitting 입력의 세 seed 평균 성능 변화는 base 대비 당뇨 AUROC +0.00091·AP +0.00240, 고혈압 AUROC −0.00018·AP +0.00208이다.
- 같은 validation 표본 256명에서 global 점수가 personal P95 위협도 이상인 비율은 당뇨의 weight 0.25/0.5/0.75/1.0에서 seed 범위 각각 66.0–70.7% / 71.9–73.8% / 76.6–77.0% / 78.9–80.5%였다. 고혈압은 62.1–66.0% / 66.4–68.4% / 68.0–69.9% / 69.5–72.3%였다.

가중치 비교에서 양 경로 중 하나가 항상 우세하지는 않지만, 이 표본에서는 global 경로가 대부분의 사용자에서 더 큰 점수를 냈다. 따라서 1회전 결과는 척도 차이를 드러냈고 사용자 행동에 따라 충분히 달라지는 가중치 설계가 필요함을 보여준다. factor별 `behavior_weight`와 소디 적용 조건은 D의 `risk_condition` 및 챌린지 정의와 함께 서윤·이경이 정한다. 결과는 연관 설명이며 좌식시간 변화의 인과효과라고 말하지 않는다.

## 결과 해석 범위

이 2024 비교 자료는 후보 변형을 선택하는 데 사용했다. 따라서 위 표는 선택 후의 독립 성능 추정치가 아니며, 이 결과로 임상 효능·외부 타당도·배포 readiness를 주장하지 않는다. 최종 선택 모델의 SHAP 기준은 2024를 포함하지 않은 2022+2023 training 전체 eligible 표본에서 다시 계산한다. 모델 threshold·위협도 등급·의료적 위험 해석도 이 결과만으로 확정하지 않는다.

## 채소 후보 추가 1회전

최신 팀 의견에 따라 `LS_VEG2`(김치·장아찌 제외)로 `vegetable_frequency`를 만들고 1\~9 범주를 one-hot 처리했다. 99는 결측이며 훈련 데이터에서만 최빈값 대치했다. 2022 train·2023 validation, seed 42·43·44로 질환별 세 번씩 추가 학습했다. 이 후보는 2024 입력 선택 비교에는 포함하지 않았고, `data/experiment-vegetable/report.json`과 개인 단위 SHAP은 ignored `data/` 아래에만 있다.

세 seed 전체 평균 변화는 당뇨 AUROC −0.00018·AP +0.00239·Brier −0.00002, 고혈압 AUROC −0.00115·AP −0.00729·Brier +0.00009다. `vegetable_intake_low`는 모든 seed의 train reference에서 양의 SHAP/P95가 있었지만 고혈압 지표가 전반적으로 나빠졌고 제품 입력 필드도 없다. 따라서 별도 요인 후보로 기록하되 final service X에는 아직 넣지 않는다. 채택하려면 C가 채소 빈도 입력·기간·DB/API 필드를 추가하고 같은 검증 설계로 feature 선택을 다시 해야 한다.

## 입력·소디 권고

- 공통 core X는 12개다. 첫 질환별 설정은 당뇨 core+sitting, 고혈압 core+sodium이다. 좌식 `BE8_1×60+BE8_2`는 별도 `sedentary_time_high` factor이며 걷기와 합치지 않는다.
- `sodium_behavior`는 `L_OUT_FQ` 외식 빈도 대리변수로만 입력한다. 실제 나트륨 섭취량·mg으로 부르거나 `LS_VEG2`와 합산하지 않는다. 2024 성능 비교상 고혈압 입력 후보로 남겼지만 validation 성능은 엇갈리고 범주별 SHAP 방향도 달라 자동 소디 챌린지 weight는 보류한다. 상세 수치와 판단은 [factor별 척도표](factor-scales.md)에 있다.
- 추천 단계에서는 `risk_condition` 충족 여부·미진단자의 양의 개인 SHAP·실제 챌린지 제공 가능 여부를 각각 확인한다. 진단자는 개인 SHAP이 없으므로 지원 factor와 승인된 행동 조건으로 A가 찬성한 binary `behavior_weight`(1=대상, 0=비대상)를 사용한다. D의 숫자 임계값은 아직 승인 전이며 결측·모름은 정상 행동 또는 자동 0으로 간주하지 않는다.
- 화면의 최근 4주 음주·외식 질문과 KNHANES 최근 1년 평균 문항은 관찰 기간이 다르다. 비슷한 빈도 범주 매핑도 근사임을 표시하고, 화면 문구와 수집 기간은 C와 합의해 고정한다.

## 재실행

2026-10-11 에 실제로 쓴 명령이다. 원시자료는 `data/raw/` 에 둔다.

```bash
uv sync --group app --group dev --group model

# canonical: 2019 를 평가 전용으로 함께 만든다
uv run --group model python scripts/model/preprocess_knhanes.py --years 2019 2022 2023 2024

# 서빙 모델: seed 42 · 2024 평가
uv run --group model --with 'shap==0.50.0' python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-refit --seeds 42 --train-years 2022 2023 --validation-years 2023 --final-variant sitting --diseases diabetes --reference-size 0
uv run --group model --with 'shap==0.50.0' python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-refit --seeds 42 --train-years 2022 2023 --validation-years 2023 --final-variant sodium --diseases hypertension --reference-size 0
uv run --group model python -m scripts.model.build_serving_artifact --diabetes data/experiment-refit/sitting-diabetes-42/artifact.json --hypertension data/experiment-refit/sodium-hypertension-42/artifact.json

# seed 변동폭과 2019 독립 평가. 출력 폴더를 나눠 report.json 이 덮어써지지 않게 한다
uv run --group model --with 'shap==0.50.0' python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-seeds/diabetes-2024 --seeds 42 43 44 --train-years 2022 2023 --validation-years 2023 --final-variant sitting --diseases diabetes --reference-size 0
uv run --group model --with 'shap==0.50.0' python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-seeds/diabetes-2019 --seeds 42 43 44 --train-years 2022 2023 --validation-years 2023 --test-years 2019 --final-variant sitting --diseases diabetes --reference-size 0
uv run --group model --with 'shap==0.50.0' python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-seeds/hypertension-2024 --seeds 42 43 44 --train-years 2022 2023 --validation-years 2023 --final-variant sodium --diseases hypertension --reference-size 0
uv run --group model --with 'shap==0.50.0' python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-seeds/hypertension-2019 --seeds 42 43 44 --train-years 2022 2023 --validation-years 2023 --test-years 2019 --final-variant sodium --diseases hypertension --reference-size 0
```
