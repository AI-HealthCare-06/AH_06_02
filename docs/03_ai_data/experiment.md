# KNHANES core·외식·좌식·채소 첫 탐색 실험

상태: 2026-10-01. 목적은 당뇨·고혈압 baseline을 한 번 학습하고 `sedentary_time_high`가 `physical_activity_low`와 별도 설명 신호를 보이는지 확인하는 것이다. 성능 최적화·임상 판단·배포 인증 실험은 아니다.

## 설계

2022 train, 2023 validation, 2024 final test 연도 분할을 사용한다. 질환별로 미진단·미복약 성인만 eligibility에 포함하고, 유효 y가 없는 행은 제외한다. 2024 test는 열지 않았다. RandomForest(200 trees, min leaf 10, max depth 10), train-only median/mode imputation과 one-hot encoding, seed 42·43·44를 썼다. SHAP 설명은 train 256명·validation 256명의 seed 고정 reference 표본이다.

| variant | feature |
|---|---|
| base | model.md의 12개 core feature |
| sodium | base + `dining_out_freq` (`sodium_behavior`) |
| sitting | base + `sitting_minutes` (`sedentary_time_high`) |
| sodium_sitting | base + 두 후보 |
| vegetable | base + `vegetable_frequency` (`vegetable_intake_low`, LS_VEG2) |

개인 위협도 P95와 전역 중요도를 2022 train SHAP sample에서 계산했다. 개인 기여도와 `global normalized_score × candidate behavior_weight`는 같은 2023 validation 사용자 SHAP sample에서 비교했다. 계산은 사용자/질환별 설명 실험용이며 256명 reference는 최종 artifact용 calibration 크기로 승인된 것이 아니다.

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

## 좌식 factor 및 척도 확인

각 seed에서 sitting model의 grouped SHAP을 `sedentary_time_high`에 따로 보존하고 `physical_activity_low`에 합치지 않았다.

- 당뇨 좌식 전역 normalized score는 18.40–20.67(순위 5–6), 2022 train sample의 positive-SHAP P95는 0.01024–0.01240이다. 고혈압은 score 8.06–8.93(순위 8–10), P95 0.01092–0.01147이다. 3 seed 모두 reference 256명에서 양의 SHAP 관측이 나왔다.
- sitting 입력의 세 seed 평균 성능 변화는 base 대비 당뇨 AUROC +0.00091·AP +0.00240, 고혈압 AUROC −0.00018·AP +0.00208이다.
- 같은 validation 표본 256명에서 global 점수가 personal P95 위협도 이상인 비율은 당뇨의 weight 0.25/0.5/0.75/1.0에서 seed 범위 각각 66.0–70.7% / 71.9–73.8% / 76.6–77.0% / 78.9–80.5%였다. 고혈압은 62.1–66.0% / 66.4–68.4% / 68.0–69.9% / 69.5–72.3%였다.

가중치 비교에서 양 경로 중 하나가 항상 우세하지는 않지만, 이 표본에서는 global 경로가 대부분의 사용자에서 더 큰 점수를 냈다. 따라서 1회전 결과는 척도 차이를 드러냈고 사용자 행동에 따라 충분히 달라지는 가중치 설계가 필요함을 보여준다. factor별 `behavior_weight`와 소디 적용 조건은 D의 `risk_condition` 및 챌린지 정의와 함께 서윤·이경이 정한다. 결과는 연관 설명이며 좌식시간 변화의 인과효과라고 말하지 않는다.

## 결과 해석 범위

2024 holdout test는 미평가다. validation 결과는 변형·seed를 고르는 탐색 지표다. 2022 training SHAP reference 256명의 95분위수는 전체 training 분포의 안정된 배포 calibration이 아니다. 최종 모델·feature를 승인한 뒤 충분한 2022 train reference에서 P95·global importance를 다시 계산해 artifact version에 고정한다. y threshold, 등급, 의료적 위험 해석도 이 결과만으로 정하지 않는다.

## 채소 후보 추가 1회전

최신 팀 의견에 따라 `LS_VEG2`(김치·장아찌 제외)로 `vegetable_frequency`를 만들고 1~9 범주를 one-hot 처리했다. 99는 결측이며 훈련 데이터에서만 최빈값 대치했다. 2022 train·2023 validation, 2024 holdout 미평가, 같은 seed 42·43·44로 질환별 세 번씩 추가 학습했다. `data/experiment-vegetable/report.json`과 개인 단위 SHAP은 ignored `data/` 아래에만 있다.

세 seed 전체 평균 변화는 당뇨 AUROC −0.00018·AP +0.00239·Brier −0.00002, 고혈압 AUROC −0.00115·AP −0.00729·Brier +0.00009다. `vegetable_intake_low`는 모든 seed의 train reference에서 양의 SHAP/P95가 있었지만 고혈압 지표가 전반적으로 나빠졌고 제품 입력 필드도 없다. 따라서 별도 요인 후보로 기록하되 final service X에는 아직 넣지 않는다. 채택하려면 C가 채소 빈도 입력·기간·DB/API 필드를 추가하고 같은 검증 설계로 feature 선택을 다시 해야 한다.

## 입력·소디 권고

- 기본 X는 core 12개다. 좌식 `BE8_1×60+BE8_2`는 `sedentary_time_high` 후보, 외식 `L_OUT_FQ`는 `sodium_behavior` 대리 지표 후보, 채소 `LS_VEG2`는 별도 `vegetable_intake_low` 후보로 분리한다.
- 소디는 `L_OUT_FQ`만 대리변수로 유지한다. 이를 실제 나트륨 섭취량·mg으로 부르거나 `LS_VEG2`와 합산하지 않는다. sodium 1회전의 당뇨 지표는 개선됐지만 고혈압 AUROC·AP는 낮아져 전 질환 final X 채택 근거로는 혼합이다. 따라서 계산 계약은 `sodium_behavior`로 한정하고, 생산용 위협도·챌린지 적용은 D와 조건 합의 및 추가 비교 전까지 후보로 둔다.
- 추천 단계에서는 `risk_condition` 충족 여부·미진단자의 양의 개인 SHAP·실제 챌린지 제공 가능 여부를 각각 확인한다. 진단자는 개인 SHAP이 없으므로 지원 factor 및 합의된 행동 조건·`behavior_weight`로 처리한다. Mapping v1에는 숫자 임계값이나 확정 `behavior_weight`가 없으므로 임의로 채우지 않는다.
- 화면의 최근 4주 음주·외식 질문과 KNHANES 최근 1년 평균 문항은 관찰 기간이 다르다. 비슷한 빈도 범주 매핑도 근사임을 표시하고, 화면 문구와 수집 기간은 C와 합의해 고정한다.

## 재실행

```bash
../model-venv/bin/python scripts/model/preprocess_knhanes.py
../model-venv/bin/python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-final --seeds 42 43 44 --variants base sodium sitting sodium_sitting
../model-venv/bin/python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-vegetable --seeds 42 43 44 --variants vegetable
```
