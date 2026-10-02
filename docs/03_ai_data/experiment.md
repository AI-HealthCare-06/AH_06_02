# KNHANES 입력 선택 및 2024 비교 평가

상태: 2026-10-01. 목적은 당뇨·고혈압의 입력 후보를 비교하고, 팀에서 요청한 2024 평가로 외식 빈도 기반 `sodium_behavior`의 적용 여부를 정하는 것이다. 결과는 실험용이며 성능 최적화·임상 판단·배포 인증이 아니다.

## 설계

2022 train, 2023 validation, 2024 비교 평가 연도 분할을 사용했다. 질환별로 미진단·미복약 성인만 eligibility에 포함하고 유효 y가 없는 행은 제외했다. RandomForest(200 trees, min leaf 10, max depth 10), train-only median/mode imputation과 one-hot encoding, seed 42·43·44를 썼다. 후보 평가 뒤 선택된 두 모델은 seed 42로 재학습해 전체 eligible 2022 train 행을 SHAP calibration reference로 다시 설명했다. 2024는 소디·입력 선택에 실제 사용했으므로 해당 선택 뒤 독립적인 최종 일반화 평가로 해석하지 않는다.

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

## 선택 모델 전체-reference 재계산

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

이 2024 비교 자료는 후보 변형을 선택하는 데 사용했다. 따라서 위 표는 선택 후의 독립 성능 추정치가 아니며, 이 결과로 임상 효능·외부 타당도·배포 readiness를 주장하지 않는다. 최종 선택 모델의 SHAP 기준은 2024를 포함하지 않은 2022 training 전체 eligible 표본에서 다시 계산한다. 모델 threshold·위협도 등급·의료적 위험 해석도 이 결과만으로 확정하지 않는다.

## 채소 후보 추가 1회전

최신 팀 의견에 따라 `LS_VEG2`(김치·장아찌 제외)로 `vegetable_frequency`를 만들고 1~9 범주를 one-hot 처리했다. 99는 결측이며 훈련 데이터에서만 최빈값 대치했다. 2022 train·2023 validation, seed 42·43·44로 질환별 세 번씩 추가 학습했다. 이 후보는 2024 입력 선택 비교에는 포함하지 않았고, `data/experiment-vegetable/report.json`과 개인 단위 SHAP은 ignored `data/` 아래에만 있다.

세 seed 전체 평균 변화는 당뇨 AUROC −0.00018·AP +0.00239·Brier −0.00002, 고혈압 AUROC −0.00115·AP −0.00729·Brier +0.00009다. `vegetable_intake_low`는 모든 seed의 train reference에서 양의 SHAP/P95가 있었지만 고혈압 지표가 전반적으로 나빠졌고 제품 입력 필드도 없다. 따라서 별도 요인 후보로 기록하되 final service X에는 아직 넣지 않는다. 채택하려면 C가 채소 빈도 입력·기간·DB/API 필드를 추가하고 같은 검증 설계로 feature 선택을 다시 해야 한다.

## 입력·소디 권고

- 공통 core X는 12개다. 첫 질환별 설정은 당뇨 core+sitting, 고혈압 core+sodium이다. 좌식 `BE8_1×60+BE8_2`는 별도 `sedentary_time_high` factor이며 걷기와 합치지 않는다.
- `sodium_behavior`는 `L_OUT_FQ` 외식 빈도 대리변수로만 입력한다. 실제 나트륨 섭취량·mg으로 부르거나 `LS_VEG2`와 합산하지 않는다. 2024 성능 비교상 고혈압 입력 후보로 남겼지만 validation 성능은 엇갈리고 범주별 SHAP 방향도 달라 자동 소디 챌린지 weight는 보류한다. 상세 수치와 판단은 [factor별 척도표](factor-scales.md)에 있다.
- 추천 단계에서는 `risk_condition` 충족 여부·미진단자의 양의 개인 SHAP·실제 챌린지 제공 가능 여부를 각각 확인한다. 진단자는 개인 SHAP이 없으므로 지원 factor와 승인된 행동 조건으로 A가 찬성한 binary `behavior_weight`(1=대상, 0=비대상)를 사용한다. D의 숫자 임계값은 아직 승인 전이며 결측·모름은 정상 행동 또는 자동 0으로 간주하지 않는다.
- 화면의 최근 4주 음주·외식 질문과 KNHANES 최근 1년 평균 문항은 관찰 기간이 다르다. 비슷한 빈도 범주 매핑도 근사임을 표시하고, 화면 문구와 수집 기간은 C와 합의해 고정한다.

## 재실행

```bash
../model-venv/bin/python scripts/model/preprocess_knhanes.py
../model-venv/bin/python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-final --seeds 42 43 44 --variants base sodium sitting sodium_sitting
../model-venv/bin/python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-vegetable --seeds 42 43 44 --variants vegetable
../model-venv/bin/python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-2024-final-full/diabetes-sitting --seeds 42 --final-variant sitting --diseases diabetes --reference-size 0
../model-venv/bin/python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-2024-final-full/hypertension-sodium --seeds 42 --final-variant sodium --diseases hypertension --reference-size 0
```
