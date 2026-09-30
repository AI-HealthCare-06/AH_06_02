# Core 입력 및 sodium·좌식·채소 후보 1회전 실험

상태: 실제 데이터 실행 대기. 좌식 독립 factor 결정은 이미 완료됐으며 이 실험은 외식 빈도(소디), 좌식시간, 채소 후보의 feature 채택과 안정성을 판단한다.

## 비교

| 실험 | 입력 |
|---|---|
| base | model.md core 12개 feature |
| sodium | base + dining_out_freq |
| sitting | base + sitting_minutes |
| vegetable | base + vegetable_frequency (검증된 열이 있을 때만) |
| sodium_sitting / sodium_vegetable / sitting_vegetable | base + 해당 후보 두 개 |
| all_candidates | base + 외식 빈도 + 좌식 + 채소 (존재·검증된 열만) |

동일 분할·하이퍼파라미터에서 seed 42·43·44를 사용한다. baseline은 RandomForestClassifier, 범주 one-hot·연속형 중앙값 대치이며 train에만 fit한다. 이 1회전의 목표는 최고 성능 확보가 아니라 실행 가능한 비교 기준 확보다.

## 산출

- 질환별 validation AUROC, AP, Brier, recall>=0.70 조건의 threshold·specificity, 유효 표본/양성 수.
- seed별 factor mean(abs(group SHAP)), 질환별 max 기준 normalized score, 방향 및 순위.
- validation reference에서 질환×factor별 positive SHAP P95, 양의 기여 관측 수, 좌식·소디 factor 안정성.
- 같은 validation 사용자에서 미진단 경로 `positive_shap/P95 → 0~100`과 진단 경로 `global normalized_score × behavior_weight`를 함께 계산하고 질환×factor별 두 score 분포와 경로별 우세 비율을 비교한다. behavior_weight는 원문 문항 척도와 D의 risk_condition을 보고 서윤·이경이 이 결과에서 확정한다. 임의 weight를 학습 결과처럼 제출하지 않는다.
- 좌식값 구간별 signed SHAP 평균은 연관 패턴 점검이며 인과효과가 아니다.
- sodium_behavior의 기여도 안정성과 P95를 같은 기준으로 확인한다.
- 선택된 변형만 2024 test 평가. 합성자료 테스트 결과를 실데이터 성능으로 쓰지 않는다.

## 채택 검토 기준 제안

validation AUROC가 두 질환 모두 base 대비 0.005 이상 하락하지 않고, 좌식의 결측·특수코드·연도별 분포에 이상이 없으며, seed별 중요도 및 구간별 해석이 과도하게 흔들리지 않으면 채택 후보로 검토한다. 이 수치는 B의 검토 기준 제안이며 팀 확정 기준이 아니다. 낮은 SHAP을 임의로 키워서 캐릭터를 만들지 않는다. 구조는 독립 factor로 유지하되 feature 미채택과 구분한다.

채소는 서비스 입력이 없으면 성능이 좋아도 MVP에 바로 채택하지 않는다. P95가 0인 factor는 `threat_eligible=false`; 임의 floor는 두지 않는다. P95가 양수여도 지나치게 작거나 seed마다 불안정한 factor의 기준은 결과를 확인한 뒤 정한다. 결합식 `global normalized_score × behavior_weight`는 합의됐고, factor별 weight 기준과 소디 위협도 적용 조건은 실제 1회전 뒤 서윤·이경이 비교 결과를 보고 확정한다.

## 실행

```bash
python -m pip install -r scripts/model/requirements.txt
python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment --seeds 42 43 44
```

출력은 로컬 data/ 아래에 둔다. raw 데이터가 아닌 집계 보고서만 검토 후 공유한다. 학습 완료 전에는 AUROC, P95 calibration, global importance 값을 채운 가짜 artifact를 제출하지 않는다. 기본 실행의 validation SHAP reference는 탐색용 256행 표본이므로 배포 calibration으로 사용하지 않는다.
