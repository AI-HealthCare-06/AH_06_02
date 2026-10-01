# B 산출물 검증 기록

2026-10-01 갱신. KNHANES 제9기 변수와 y/eligibility 매핑을 확인하고 ignored `data/`에서 전처리·오프라인 모델 실험을 실행했다. 개인 단위 자료와 SHAP 출력은 저장소에 넣지 않는다.

| 검사 | 결과 |
|---|---|
| KNHANES 원자료 | 2022~2024 20,191행 확인; 만 19세 이상 canonical 17,262행 생성(2022 5,322, 2023 5,907, 2024 6,033); 연도별 ID 중복 0 |
| 코드 매핑 | 성별·흡연·음주·걷기·근력·좌식·외식·가족력 및 질환 eligibility 코드를 KNHANES 제9기 지침과 원자료 value labels/domain에 대조 |
| 당뇨·고혈압 모델 | 기본·소디·좌식 4 variants × 2 diseases × 3 seeds = 24; 별도 LS_VEG2 채소 variant 2 diseases × 3 seeds = 6. 2022 train, 2023 validation; 2024 holdout은 미평가 |
| Label 누수 | 질환별 미진단·미복약 대상을 분리; valid y 코드만 사용; 혈압·혈당·진단·약물 원변수는 X에서 제외 |
| SHAP | probability-space, factor별 signed grouping, 가산성 오차 <= 0.01; global mean absolute grouped SHAP 및 질환별 max=100 score 산출 |
| 위협도·진단자 비교 | 2022 train SHAP reference 256명으로 positive P95; 같은 validation 사용자 256명에서 `global × weight` 후보와 personal threat를 비교. 탐색용 추정치이며 배포 calibration 아님 |
| 좌식 독립성 | sitting 변형 세 seed 모두 좌식 양수 grouped SHAP 및 양수 train P95 관찰; 각 질환 성능 비교 완료; 결과는 연관 설명이지 인과 아님 |
| 채소 후보 | LS_VEG2 1~9와 99 결측을 세 연도 값 영역과 대조하고 canonical 변환 단위 테스트 및 6회 validation ablation 완료. 제품 서비스 입력 없음, 최종 X 미선정 |
| API 계약 | 지정 API 명세서 B 탭의 3 endpoints 및 조회·폴링 응답을 문서와 대조 |
| ERD 쓰기/NULL 계약 | 지정 테이블 명세에서 여섯 설명 필드 및 `source_prediction_id` 질환별 NULL 의미를 확인 |
| 데이터 비공개 | `.gitignore`에서 `data/` 제외; `git status` 및 staged file 목록에서 원자료·개인별 output이 없는지 확인 후 commit |

실제 모델 지표와 요인별 결과는 `experiment.md`에 요약한다. 이 비교는 소규모 고정 SHAP sample의 첫 회전이며, 2024 test, 승인된 feature/model 선택, calibration 재확인, API 서버 통합이나 배포 검증을 의미하지 않는다. 개인 단위 SHAP와 모델 파일은 `data/` 밖으로 공유하지 않는다.

기본 확인 명령:

```bash
../model-venv/bin/python -m unittest discover -s tests/model_contract -v
git diff --check
git status --short
```
