# 좌식시간 및 채소 후보 1회전 실험

상태: 실제 데이터 실행 대기. 좌식 독립 factor 결정은 이미 완료됐으며 이 실험은 모델 feature 채택과 안정성을 판단한다.

## 비교

| 실험 | 입력 |
|---|---|
| base | model.md 기본 13개 feature |
| sitting | base + sitting_minutes |
| vegetable | base + vegetable_frequency (검증된 열이 있을 때만) |
| both | base + 좌식 + 채소 |

동일 분할·하이퍼파라미터에서 seed 42·43·44를 사용한다. baseline은 RandomForestClassifier, 범주 one-hot·연속형 중앙값 대치이며 train에만 fit한다. 이 1회전의 목표는 최고 성능 확보가 아니라 실행 가능한 비교 기준 확보다.

## 산출

- 질환별 validation AUROC, AP, Brier, recall>=0.70 조건의 threshold·specificity, 유효 표본/양성 수.
- seed별 factor mean(abs(group SHAP)), 방향 및 순위, 좌식 feature 포함 전후 차이.
- 좌식값 구간별 signed SHAP 평균은 연관 패턴 점검이며 인과효과가 아니다.
- sodium_behavior의 기여도 안정성도 같은 기준으로 확인한다.
- 선택된 변형만 2024 test 평가. 합성자료 테스트 결과를 실데이터 성능으로 쓰지 않는다.

## 채택 검토 기준 제안

validation AUROC가 두 질환 모두 base 대비 0.005 이상 하락하지 않고, 좌식의 결측·특수코드·연도별 분포에 이상이 없으며, seed별 중요도 및 구간별 해석이 과도하게 흔들리지 않으면 채택 후보로 검토한다. 이 수치는 B의 검토 기준 제안이며 팀 확정 기준이 아니다. 낮은 SHAP을 임의로 키워서 캐릭터를 만들지 않는다. 구조는 독립 factor로 유지하되 feature 미채택과 구분한다.

채소는 서비스 입력이 없으면 성능이 좋아도 MVP에 바로 채택하지 않는다. 소디 fallback은 검증 후 D와 별도 계약한다.

## 실행

```bash
python -m pip install -r scripts/model/requirements.txt
python scripts/model/run_baseline.py --data data/canonical.csv --out data/experiment --seeds 42 43 44
```

출력은 로컬 data/ 아래에 둔다. raw 데이터가 아닌 집계 보고서만 검토 후 공유한다. 학습 완료 전에는 AUROC, HP scale, global importance 값을 채운 가짜 artifact를 제출하지 않는다.
