# KNHANES core·외식·좌식 첫 탐색 실험

상태: 2026-10-01. 목적은 당뇨·고혈압 baseline을 한 번 학습하고 `sedentary_time_high`가 `physical_activity_low`와 별도 설명 신호를 보이는지 확인하는 것이다. 성능 최적화·임상 판단·배포 인증 실험은 아니다.

## 설계

2022 train, 2023 validation, 2024 final test 연도 분할을 사용한다. 질환별로 미진단·미복약 성인만 eligibility에 포함하고, 유효 y가 없는 행은 제외한다. 2024 test는 열지 않았다. RandomForest(200 trees, min leaf 10, max depth 10), train-only median/mode imputation과 one-hot encoding, seed 42·43·44를 썼다. SHAP 설명은 train 256명·validation 256명의 seed 고정 reference 표본이다.

| variant | feature |
|---|---|
| base | model.md의 12개 core feature |
| sodium | base + `dining_out_freq` (`sodium_behavior`) |
| sitting | base + `sitting_minutes` (`sedentary_time_high`) |
| sodium_sitting | base + 두 후보 |

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

각 행은 seed 42·43·44의 평균이다. 각 변형은 당뇨 validation n=4,838·양성 194, 고혈압 n=4,143·양성 381로 평가됐다. 보고서 `data/experiment-final/report.json`은 `.gitignore` 아래 로컬에만 둔다. 개인 단위 특징·행 SHAP을 Git이나 Slack에 올리지 않는다.

## 좌식 factor 및 척도 확인

각 seed에서 sitting model의 grouped SHAP을 `sedentary_time_high`에 따로 보존하고 `physical_activity_low`에 합치지 않았다.

- 당뇨 좌식 전역 normalized score는 18.40–20.67(순위 5–6), 2022 train sample의 positive-SHAP P95는 0.01024–0.01240이다. 고혈압은 score 8.06–8.93(순위 8–10), P95 0.01092–0.01147이다. 3 seed 모두 reference 256명에서 양의 SHAP 관측이 나왔다.
- sitting 입력의 세 seed 평균 성능 변화는 base 대비 당뇨 AUROC +0.00091·AP +0.00240, 고혈압 AUROC −0.00018·AP +0.00208이다.
- 같은 validation 표본 256명에서 global 점수가 personal P95 위협도 이상인 비율은 당뇨의 weight 0.25/0.5/0.75/1.0에서 seed 범위 각각 66.0–70.7% / 71.9–73.8% / 76.6–77.0% / 78.9–80.5%였다. 고혈압은 62.1–66.0% / 66.4–68.4% / 68.0–69.9% / 69.5–72.3%였다.

가중치 비교에서 양 경로 중 하나가 항상 우세하지는 않지만, 이 표본에서는 global 경로가 대부분의 사용자에서 더 큰 점수를 냈다. 따라서 1회전 결과는 척도 차이를 드러냈고 사용자 행동에 따라 충분히 달라지는 가중치 설계가 필요함을 보여준다. factor별 `behavior_weight`와 소디 적용 조건은 D의 `risk_condition` 및 챌린지 정의와 함께 서윤·이경이 정한다. 결과는 연관 설명이며 좌식시간 변화의 인과효과라고 말하지 않는다.

## 결과 해석 범위

2024 holdout test는 미평가다. validation 결과는 변형·seed를 고르는 탐색 지표다. 2022 training SHAP reference 256명의 95분위수는 전체 training 분포의 안정된 배포 calibration이 아니다. 최종 모델·feature를 승인한 뒤 충분한 2022 train reference에서 P95·global importance를 다시 계산해 artifact version에 고정한다. y threshold, 등급, 의료적 위험 해석도 이 결과만으로 정하지 않는다.

채소 feature는 서비스의 공통 입력 필드·기간이 확정되지 않아 이번 ablation에서 제외했다. 외식 빈도는 나트륨 섭취량의 대리변수일 뿐이며, 당뇨·고혈압 모델 점수 개선만으로 나트륨 요인을 임상 지표로 해석하지 않는다.

## 재실행

```bash
../model-venv/bin/python scripts/model/preprocess_knhanes.py
../model-venv/bin/python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment-final --seeds 42 43 44 --variants base sodium sitting sodium_sitting
```
