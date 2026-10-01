# 홍서윤 B 담당 항목 진행 현황

기준일: 2026-10-01 KST. 팀원이 직접 관리하는 Notion 체크박스는 작업자가 대신 변경하지 않는다.

| 항목 | 완료한 내용 | 상태 |
|---|---|---|
| 전역 중요도 정규화 | 지표 `mean(|grouped SHAP|)`, 질환별 최대값을 100으로 둔 `importance / max × 100`, `model_version`별 고정 기준을 Slack에 공유 | 의견 공유 완료 |
| X·y 고정 | KNHANES 9기 2022~2024 코드·특수값 대조, core X 12개와 당뇨·고혈압 y/eligibility 정의 및 검사값 누수 차단을 문서화 | 문서·전처리 완료 |
| KNHANES 전처리 | 성인 17,262행 canonical 데이터와 집계 audit 생성. 원자료·개인별 결과는 `.gitignore` 아래 로컬 `data/`에만 보관 | 로컬 완료·비공개 |
| 두 질환 1회전 | 당뇨·고혈압 × base/sodium/sitting/sodium_sitting × seed 42/43/44, 24회; LS_VEG2 채소 후보 × 두 질환 × 같은 seed 6회 추가 | 총 30회 탐색 완료; 2024 미평가 |
| LS_VEG 채소 후보 | `LS_VEG2`(김치·장아찌 제외) 1~9 범주를 별도 `vegetable_intake_low`로 전처리·ablation. 당뇨 AP +0.00239, 고혈압 AP −0.00729 등 성능이 엇갈려 final X에 미채택 | 후보 검증 완료; 서비스 입력 필드·성능 합의 대기 |
| `docs/model.md` | X/y, 혈압·혈당 누수 제외, P95 기준, 요인/NULL/API 계약 정리. 자세한 기술 근거는 `docs/03_ai_data/model.md` | 완료 |
| API 3개 | 예측 접수·상태/결과 조회(폴링)·기여도 조회를 지정 B 탭 기준으로 문서화 | 완료·시트 대조 |
| 전역 중요도 `normalized_score` | `mean(|grouped SHAP|)`를 질환별 최대값에 정규화하고 버전 고정해 반환하도록 내부 계약 정리 | 계약·의견 완료; production artifact 미선정 |
| ERD 여섯 칸 및 `source_prediction_id` | 원본 테이블 명세 시트에서 `input_snapshot`, `disease`, `contribution`, `direction`, `rank`, `source_prediction_id` 설명 확인. 진단자 전역 경로·보너스 챌린지는 NULL, 미진단 SHAP 추천은 예측 ID | 확인·시트 반영 완료 |
| 용어 | 사용자 문구를 위협도·공략 점수로 갱신하고 DB/API 식별자는 호환을 위해 유지 | 완료 |
| 좌식시간 factor | 독립 `sedentary_time_high`로 세 seed 양수 SHAP/P95 및 전역 rank 확인, validation 성능 비교 | 근거 공유 가능; 앱 feature 최종 채택은 팀 판단 |
| 진단자 `behavior_weight` | 동일 validation 사용자에서 personal P95 점수와 global×후보 weight를 비교 | 분포 산출; factor별 weight·risk_condition 최종 합의 대기 |
| GitHub 제출 | `AI-HealthCare-06/AH_06_02`의 `feature/knhanes-b-deliverables`에 푸시, 최신 main 동기화, [draft PR #7](https://github.com/AI-HealthCare-06/AH_06_02/pull/7) 생성. 기존 PR #2는 수정하지 않음 | 제출·리뷰 대기 |
| Notion 제출 링크 | 지정 SHARE DOCUMENTS 페이지를 연결된 Notion에서 찾지 못함(직접 조회 404, 검색 결과 없음) | 외부 접근 차단; 정확한 페이지 공유/접근 필요 |

## 실험 요약

세 seed 평균 validation AUROC는 base 대비 sitting 변형에서 당뇨 +0.0009, 고혈압 −0.0002였다. Average precision은 각각 +0.0024, +0.0021이다. 좌식 factor는 당뇨 global normalized score 18.4–20.7(5–6위), 고혈압 8.1–8.9(8–10위)였으며 각 seed의 2022 train SHAP reference에서 양수 P95가 관찰됐다. 이는 독립 요인 설명의 탐색 근거이지 인과효과나 제품 최종 채택 근거로 단정하지 않는다.

소디 `L_OUT_FQ`는 실제 나트륨 섭취량이 아닌 외식 빈도 대리 지표로만 유지하는 안이다. sodium ablation의 당뇨 평균 AUROC/AP는 base 대비 +0.00525/+0.00305, 고혈압은 −0.00320/−0.00321이므로 전 질환 final X 채택 근거는 혼합이다. Mapping v1의 `risk_condition` 숫자 임계값과 `behavior_weight`는 확정되지 않았다.

2022 train에서 256명, validation에서 256명을 뽑아 위협도 reference와 같은 사용자 비교를 수행했다. 따라서 P95 및 중요도는 작은 reference sample 기반의 탐색치다. 2024 test는 열지 않았다. 공유용 입력 코드표는 `docs/03_ai_data/input-code-map.md`, 실험 조건·수치는 `docs/03_ai_data/experiment.md`에 있다.

## 남은 결정과 제출 의존성

- 배포 모델을 정하면 전체 또는 사전 합의한 충분한 2022 training reference에서 global importance/P95를 다시 계산하고 고정 artifact를 만든다.
- 진단자 경로는 한 후보 weight도 항상 우세하지 않지만 좌식 factor 비교에서 global 점수가 대체로 더 높았다. factor별 `behavior_weight`와 risk_condition 숫자 임계값은 확정 대기다. 행동 조건·개인 SHAP 부호·챌린지 제공 여부를 별도 판정하도록 김이경님과 정리한다.
- 2024 holdout 평가, threshold·등급 확정, deployable model artifact, API 서버 통합은 탐색 실험 밖이다.
- Notion의 SHARE DOCUMENTS에 링크를 걸어야 제출 인정된다는 팀 규칙은 유지된다. 이 연결에서 해당 페이지를 읽거나 편집할 수 없어, PR 링크를 Notion 제출 링크로 대체할 수 없다.

## 근거

- [지정 API 명세서 — B 탭](https://docs.google.com/spreadsheets/d/1YGAncv-rZBLBvrVFjlk7yg1kP7fabZunzYmOZz8C9OE/edit?gid=1286618417#gid=1286618417)
- [API 명세서 원본](https://docs.google.com/spreadsheets/d/1KZMhGHa7s2y3XSPKfA2rcTeJgTsUVi7c/edit?gid=1571297883#gid=1571297883)
- [전역 중요도·개인 위협도 논의](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790744047761599?thread_ts=1790744047.761599)
- [좌식 분리 결정](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790564317593679)
- [9/30 B 파트 계약 요약](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790755600857999)
- [2026-10-01 모델 입력코드 문의 스레드](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790820503219129)
- [입력 코드 및 1회전 결과 공유](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790824382158959?thread_ts=1790820503.219129)
