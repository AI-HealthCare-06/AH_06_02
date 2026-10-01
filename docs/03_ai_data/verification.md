# B 산출물 검증 기록

2026-10-01 갱신. KNHANES 제9기 변수와 y/eligibility 매핑을 확인하고 ignored `data/`에서 전처리·오프라인 모델 실험을 실행했다. 개인 단위 자료와 SHAP 출력은 저장소에 넣지 않는다.

| 검사 | 결과 |
|---|---|
| KNHANES 원자료 | 2022~2024 20,191행 확인; 만 19세 이상 canonical 17,262행 생성(2022 5,322, 2023 5,907, 2024 6,033); 연도별 ID 중복 0 |
| 코드 매핑 | 성별·흡연·음주·걷기·근력·좌식·외식·가족력 및 질환 eligibility 코드를 KNHANES 제9기 지침과 원자료 value labels/domain에 대조 |
| 걷기·음주 특수값 재대조 | 성인 17,262명에서 BE3_32/33의 88 각각 2,291건은 BE3_31=1과 일치해 0분/회; BE3_31=99 1,508건과 시간 변수 99 각 1,532건은 결측. BD1_11=8 1,856건 전부 BD1=1·BD2_1=8이라 빈도1·양0 처리; 전처리 출력 단위검증 통과 |
| 당뇨·고혈압 모델 | validation 후보 30회 완료. base/sodium/sitting/sodium_sitting 4 variants × 2 diseases × 3 seeds = 24회는 2024 비교 평가도 실행; 당뇨 core+sitting·고혈압 core+sodium 선택 |
| Label 누수 | 질환별 미진단·미복약 대상을 분리; valid y 코드만 사용; 혈압·혈당·진단·약물 원변수는 X에서 제외 |
| SHAP | probability-space, factor별 signed grouping, 가산성 오차 <= 0.01; global mean absolute grouped SHAP 및 질환별 max=100 score 산출 |
| 위협도·진단자 비교 | validation 사용자 256명에서 후보식을 비교. 선택 모델 seed 42의 P95·global importance는 전체 eligible 2022 training reference로 재계산; 정밀도 1e-5 및 P95 상위 꼬리 기대 n≥20 기준으로 24개 조합 모두 `threat_eligible=true` |
| 좌식 독립성 | sitting 변형 세 seed 모두 좌식 양수 grouped SHAP 및 양수 train P95 관찰; 각 질환 성능 비교 완료; 결과는 연관 설명이지 인과 아님 |
| 채소 후보 | LS_VEG2 1~9와 99 결측을 세 연도 값 영역과 대조하고 canonical 변환 단위 테스트 및 6회 validation ablation 완료. 제품 서비스 입력 없음, 최종 X 미선정 |
| API 계약 | 지정 API 명세서 B 탭의 3 endpoints 및 조회·폴링 응답을 문서와 대조 |
| ERD 쓰기/NULL 계약 | Slack 제공 테이블 명세 v2-1에서 여섯 설명 필드 및 `source_prediction_id` 질환별 NULL 의미를 확인하고 로컬 수정 사본 생성 |
| 데이터 비공개 | `.gitignore`에서 `data/` 제외; `git status` 및 staged file 목록에서 원자료·개인별 output이 없는지 확인 후 commit |

실제 모델 지표는 `experiment.md`, 질환×factor별 원 `mean(|SHAP|)`·P95·`threat_eligible` 값은 `factor-scales.md`에 기록한다. 2024 평가를 feature selection에 썼으므로 그 선택 뒤 독립 일반화 성능으로 해석하지 않는다. API 서버 통합·배포 검증은 완료하지 않았다. 개인 단위 SHAP와 모델 파일은 `data/` 밖으로 공유하지 않는다.

기본 확인 명령:

```bash
../model-venv/bin/python -m unittest discover -s tests/model_contract -v
git diff --check
git status --short
```
