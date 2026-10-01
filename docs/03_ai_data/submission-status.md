# 홍서윤 B 담당 항목 진행 현황

기준일: 2026-10-01 KST. 팀원이 직접 관리하는 Notion 체크박스는 작업자가 대신 변경하지 않는다.

| 항목 | 완료한 내용 | 상태 |
|---|---|---|
| 전역 중요도 정규화 | 지표 `mean(|grouped SHAP|)`, 질환별 최대값을 100으로 둔 `importance / max × 100`, `model_version`별 고정 기준을 Slack에 공유 | 의견 공유 완료 |
| X·y 고정 | KNHANES 9기 2022~2024 코드·특수값 대조, core X 12개와 당뇨·고혈압 y/eligibility 정의 및 검사값 누수 차단을 문서화 | 문서·전처리 완료 |
| KNHANES 전처리 | 성인 17,262행 canonical 데이터와 집계 audit 생성. 원자료·개인별 결과는 `.gitignore` 아래 로컬 `data/`에만 보관 | 로컬 완료·비공개 |
| 두 질환 1회전 | KNHANES 전처리와 validation 후보 30회 완료; 기본·소디·좌식 후보 24회는 seed 42/43/44로 2024 비교 평가도 완료 | 당뇨 core+sitting, 고혈압 core+sodium 첫 실험 입력 선택; 평가 결과는 후보 선택에 사용 |
| LS_VEG 채소 후보 | `LS_VEG2`(김치·장아찌 제외) 1~9 범주를 별도 `vegetable_intake_low`로 전처리·ablation. 당뇨 AP +0.00239, 고혈압 AP −0.00729 등 성능이 엇갈려 final X에 미채택 | 후보 검증 완료; 서비스 입력 필드·성능 합의 대기 |
| `docs/model.md` | X/y, 혈압·혈당 누수 제외, P95 기준, 요인/NULL/API 계약 정리. 자세한 기술 근거는 `docs/03_ai_data/model.md` | 완료 |
| API 3개 | 예측 접수·상태/결과 조회(폴링)·기여도 조회를 지정 B 탭 기준으로 문서화 | 완료·시트 대조 |
| 전역 중요도 `normalized_score` | 지표 `mean(|grouped SHAP|)`, 질환별 최대값 100 정규화 계약 확인. 선택된 seed 42 모델에서 전체 2022 eligible 표본으로 P95·전역 중요도 재계산 | 실험 reference 재계산 완료; 배포 artifact/version 생성 대기 |
| ERD 여섯 칸 및 `source_prediction_id` | Slack 제공 v2-1에서 설명 여섯 칸과 진단자 NULL·미진단 prediction ID 경로를 검토했다. 파일은 185컬럼이라고 적혀 있지만 저장소 기준은 186컬럼이라 로컬 검토본에만 기록했다 | B 필드 검토 완료; 전체 최신본 여부와 원본 시트 반영은 확인 필요 |
| 용어 | 사용자 문구를 위협도·공략 점수로 갱신하고 DB/API 식별자는 호환을 위해 유지 | 완료 |
| 좌식시간 factor | 독립 `sedentary_time_high`로 세 seed SHAP·validation·2024 성능 비교. 당뇨 첫 실험 모델에 추가 | 실험 입력 결정; 앱 적용은 C/D 계약 확인 필요 |
| 진단자 `behavior_weight` | 동일 validation 사용자에서 personal P95 점수와 global×후보 weight를 비교 | 분포 산출; factor별 weight·risk_condition 최종 합의 대기 |
| GitHub 제출 | 기존 B 전달 [PR #7](https://github.com/AI-HealthCare-06/AH_06_02/pull/7)은 main에 병합됨. 2024 비교 평가와 전체-reference 척도 재계산은 [후속 PR #9](https://github.com/AI-HealthCare-06/AH_06_02/pull/9)에 제출 | CI 통과·리뷰 대기 |
| Notion 제출 링크 | 지정 SHARE DOCUMENTS 페이지를 연결된 Notion에서 찾지 못함(직접 조회 404, 검색 결과 없음) | 외부 접근 차단; 정확한 페이지 공유/접근 필요 |

## 실험 요약

2024 3-seed 평균에서 당뇨 core+sitting은 base 대비 AP +0.002438·Brier −0.000025·AUROC −0.002236이었고, 고혈압 core+sodium은 AP +0.005599·AUROC +0.001400·Brier −0.000101이었다. 이 평가가 입력 선택에 쓰였으므로 수치는 독립 test 일반화 성능으로 제시하지 않는다.

소디 `L_OUT_FQ`는 실제 나트륨 섭취량이 아닌 외식 빈도 대리 지표로, 모델에는 고혈압만 포함했다. 팀 합의대로 진단자 챌린지 추천의 숫자 `risk_condition`과 factor별 `behavior_weight`는 아직 결정되지 않았다.

선택 모델은 seed 42로 다시 학습했고 P95와 전역 중요도를 전체 eligible 2022 training 표본에서 재계산했다. 로컬 산출물은 `.gitignore` 아래에만 있다. 공유용 입력 코드표는 `docs/03_ai_data/input-code-map.md`, 실험 조건·수치는 `docs/03_ai_data/experiment.md`에 있다.

## 남은 결정과 제출 의존성

- 배포용 artifact/version, 서비스/API 통합 및 별도 독립 외부 검증은 남아 있다. 지금 결과는 선택용 로컬 실험이며 배포 모델이 아니다.
- risk condition 전 validation 256명 비교에서는 선택한 좌식·소디 요인 모두 global 경로가 다수 사용자에서 개인 점수보다 높았다(좌식 71.9–83.6%, 소디 85.9–92.6% across candidate weights). 조건을 적용한 뒤 같은 비교를 해야 하므로 `behavior_weight`와 숫자 risk_condition은 임의 확정하지 않았다. 김이경님과 행동 조건을 정한 뒤 조건부 분포를 확인해야 한다.
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
