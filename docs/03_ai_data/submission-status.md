# 홍서윤 B 담당 항목 진행 현황

기준일: 2026-10-01 KST. 팀원이 직접 관리하는 Notion 체크박스는 작업자가 대신 변경하지 않는다.

| 항목 | 완료한 내용 | 상태 |
|---|---|---|
| 전역 중요도 정규화 | 지표 `mean(|grouped SHAP|)`, 질환별 최대값을 100으로 둔 `importance / max × 100`, `model_version`별 고정 기준을 Slack에 공유 | 의견 공유 완료 |
| X·y 고정 | KNHANES 9기 2022~2024 코드·특수값 대조, core X 12개와 당뇨·고혈압 y/eligibility 정의 및 검사값 누수 차단을 문서화 | 문서·전처리 완료 |
| KNHANES 전처리 | 성인 17,262행 canonical 데이터와 집계 audit 생성. 원자료·개인별 결과는 `.gitignore` 아래 로컬 `data/`에만 보관 | 로컬 완료·비공개 |
| 두 질환 1회전 | KNHANES 전처리, 30회 후보 탐색, seed 42/43/44의 2024 비교, 선택 모델 seed 42 전체 2022-reference 재학습·SHAP 산출 완료 | 선택 실험 모델 산출 완료; 2024가 후보 선택에 사용되어 독립 일반화 성능이나 배포 승인을 뜻하지 않음 |
| LS_VEG 채소 후보 | `LS_VEG2`(김치·장아찌 제외) 1~9 범주를 별도 `vegetable_intake_low`로 전처리·ablation. 당뇨 AP +0.00239, 고혈압 AP −0.00729 등 성능이 엇갈려 final X에 미채택 | 후보 검증 완료; 서비스 입력 필드·성능 합의 대기 |
| `docs/model.md` | X/y, 혈압·혈당 누수 제외, P95 기준, 요인/NULL/API 계약 정리. 자세한 기술 근거는 `docs/03_ai_data/model.md` | 완료 |
| API 3개 | 예측 접수·상태/결과 조회(폴링)·기여도 조회를 지정 B 탭 기준으로 문서화 | 완료·시트 대조 |
| 전역 중요도·positive SHAP 기준값 | 선택 모델의 질환×factor별 `mean(|grouped SHAP|)`, `positive_shap_p95`, `positive_n`, normalized score를 전체 2022 eligible reference에서 산출해 [`factor-scales.md`](factor-scales.md)에 기록 | 산출 완료; report/artifact에 `threat_eligible` 판정도 포함 |
| ERD 여섯 칸 및 `source_prediction_id` | Slack 제공 v2-1에서 설명 여섯 칸과 진단자 NULL·미진단 prediction ID 경로를 검토했다. 파일은 185컬럼이라고 적혀 있지만 저장소 기준은 186컬럼이라 로컬 검토본에만 기록했다 | B 필드 검토 완료; 전체 최신본 여부와 원본 시트 반영은 확인 필요 |
| 용어 | 사용자 문구를 위협도·공략 점수로 갱신하고 DB/API 식별자는 호환을 위해 유지 | 완료 |
| 좌식시간 factor | 독립 `sedentary_time_high`로 세 seed SHAP·validation·2024 성능 비교. 당뇨 첫 실험 모델에 추가 | 실험 입력 결정; 앱 적용은 C/D 계약 확인 필요 |
| 진단자 `behavior_weight` | 2026-10-01 Slack에서 A가 MVP 사용자별 이진 weight(적용 1 / 비적용 0)에 찬성. 누락·모름은 별도 미평가. 기존 0.25/0.5/0.75/1.0 비교는 탐색 결과로 분리 | weight 척도 합의; factor별 행동 cutoff는 D의 숫자 조건표·팀 승인 대기 |
| GitHub 제출 | 기존 B 전달 [PR #7](https://github.com/AI-HealthCare-06/AH_06_02/pull/7)은 main에 병합됨. 2024 비교 평가와 전체-reference 척도 재계산은 [후속 PR #9](https://github.com/AI-HealthCare-06/AH_06_02/pull/9)에 제출 | CI 통과·리뷰 대기 |
| Notion 제출 링크 | 지정 SHARE DOCUMENTS 페이지를 연결된 Notion에서 찾지 못함(직접 조회 404, 검색 결과 없음) | 외부 접근 차단; 정확한 페이지 공유/접근 필요 |

## 실험 요약

2024 3-seed 평균에서 당뇨 core+sitting은 base 대비 AP +0.002438·Brier −0.000025·AUROC −0.002236이었고, 고혈압 core+sodium은 AP +0.005599·AUROC +0.001400·Brier −0.000101이었다. 이 평가가 입력 선택에 쓰였으므로 수치는 독립 test 일반화 성능으로 제시하지 않는다.

소디 `L_OUT_FQ`는 실제 나트륨 섭취량이 아닌 외식 빈도 대리 지표로, 실험에는 고혈압만 포함했다. 2024 비교에서는 소폭 개선이 있었지만 2023 validation AP는 낮았고, 범주별 SHAP 방향도 단조롭지 않다. 따라서 모델 요인값은 산출했어도 “외식 감소” 챌린지의 숫자 `risk_condition`이나 자동 weight를 확정하지 않았다.

선택 모델은 seed 42로 다시 학습했고 P95와 전역 중요도를 전체 eligible 2022 training 표본에서 재계산했다. 로컬 산출물은 `.gitignore` 아래에만 있다. 공유용 입력 코드표는 `docs/03_ai_data/input-code-map.md`, 실험 조건·수치는 `docs/03_ai_data/experiment.md`에 있다.

## 남은 결정과 제출 의존성

- 배포용 artifact/version, 서비스/API 통합 및 별도 독립 외부 검증은 남아 있다. 지금 결과는 선택용 로컬 실험이며 배포 모델이 아니다.
- 숫자 행동 조건표(BMI·허리·활동·좌식·음주)와 그 조건 아래의 0/1 weight 집계는 D 초안·팀 승인 후 마무리해야 한다. 좌식·외식의 이전 0.25/0.5/0.75/1.0 comparison은 조건을 적용하지 않은 탐색용이며 MVP weight로 오인하지 않는다.
- `sodium_behavior`는 raw `L_OUT_FQ` 범주를 그대로 쓰는 고혈압 실험 factor다. 실제 나트륨량으로 환산하지 않으며, 코드 방향에 따른 SHAP 부호가 섞여 있어 “외식 감소” 추천 weight는 보류한다. [척도표](factor-scales.md)에 관측값을 남겼다.
- 2024 자료로 입력 변형을 골랐으므로 향후 독립 자료의 성능 평가가 필요하다. y 판정 threshold·위협도 등급·의료적 해석과 API 서버 통합은 이 실험에서 확정하지 않았다.
- Notion의 SHARE DOCUMENTS에 링크를 걸어야 제출 인정된다는 팀 규칙은 유지된다. 이 연결에서 해당 페이지를 읽거나 편집할 수 없어, PR 링크를 Notion 제출 링크로 대체할 수 없다.

## 근거

- [지정 API 명세서 — B 탭](https://docs.google.com/spreadsheets/d/1YGAncv-rZBLBvrVFjlk7yg1kP7fabZunzYmOZz8C9OE/edit?gid=1286618417#gid=1286618417)
- [API 명세서 원본](https://docs.google.com/spreadsheets/d/1KZMhGHa7s2y3XSPKfA2rcTeJgTsUVi7c/edit?gid=1571297883#gid=1571297883)
- [전역 중요도·개인 위협도 논의](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790744047761599?thread_ts=1790744047.761599)
- [좌식 분리 결정](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790564317593679)
- [9/30 B 파트 계약 요약](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790755600857999)
- [2026-10-01 모델 입력코드 문의 스레드](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790820503219129)
- [입력 코드 및 1회전 결과 공유](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790824382158959?thread_ts=1790820503.219129)
