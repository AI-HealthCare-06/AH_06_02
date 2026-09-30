# 홍서윤 B 담당 항목 진행 현황

기준일: 2026-09-30 KST. Notion의 본인 체크박스는 사용자 지시에 따라 직접 변경하지 않는다.

| 오늘 항목 | 결과 | 상태 |
|---|---|---|
| 전역 중요도 정규화 의견 확인 | 원값 `mean(|grouped SHAP|)`, 화면용 `importance / 질환별 max * 100`, 최대값은 `model_version`별 고정으로 정리해 Slack에 공유 | 의견 공유 완료 |
| X·y 정의 고정 | core 12개 입력과 당뇨·고혈압 각각의 y 정의, 누수 차단 변수를 model.md에 반영 | 정의 문서화 완료; 공식 코드북 검증 대기 |
| 당뇨·고혈압 1회전 학습 | 두 질환 모델, sodium·좌식·채소 후보 ablation 및 reference P95 보고를 실행할 수 있게 스크립트를 정리 | 원자료·코드북 미확보로 실행 불가 |
| docs/model.md | 전역 중요도, 개인 위협도 P95, 좌식 독립 factor, 소디 후보, 진단자 경로와 확정 대기값을 반영 | 수정 완료 |
| ERD 6개 항목 | 확보된 ERD SQL에서 predictions.input_snapshot, prediction_contributions.disease/contribution/direction/rank, user_challenges.source_prediction_id 확인 | 6개 존재; source_prediction_id NULL 허용 및 진단자 NULL 확인 |
| 용어 | 사용자 표기를 위협도·공략 점수로 갱신. DB/API 식별자는 계약 유지 | 문서 반영 완료 |
| behavior_weight·소디 위협도 | 실제 SHAP 분포와 양의 기여 P95, 안정성 결과를 보고 확정 | 1회전 후 결정 |

## 남은 외부 의존성

- 프로젝트 폴더에서 KNHANES 2022~2024 원시 `.sav`와 공식 연도별 코드북을 찾지 못했다. 그래서 실제 학습 결과·AUROC·SHAP·소디 안정성·`behavior_weight` 변환값은 없다. 실행 준비 코드의 표본·합성 테스트 결과를 실데이터 결과로 표시하지 않는다.
- 확인 가능한 로컬 ERD SQL은 여섯 컬럼을 포함하지만 Slack에서는 더 최신 185컬럼 ERD 변경이 언급됐다. 최신 첨부본과의 동일성은 아직 대조하지 못했다.
- 지정 API 시트의 모듈 호출 F9는 `get_global_importance()` 반환을 `[{factor_key, importance, rank, model_version}]`로 규정한다. 반환은 rank 오름차순이므로 D가 rank 1의 importance를 질환별 max로 사용해 표시용 0~100 점수를 계산하도록 문서화했다. 공유 반환 스키마는 그대로 유지한다.
- 제출 저장소: [AH_06_02 PR #2](https://github.com/AI-HealthCare-06/AH_06_02/pull/2).

## 확인한 대화와 문서

- [9/30 B 파트 모델·X/y·용어 요약](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790755600857999)
- [오늘 문서·실험 상태 공유](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790757885765989)
- [전역 중요도·개인 위협도 정규화 논의](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790744047761599?thread_ts=1790744047.761599)
- [지정 API 명세서](https://docs.google.com/spreadsheets/d/1KZMhGHa7s2y3XSPKfA2rcTeJgTsUVi7c/edit?gid=1571297883#gid=1571297883)
- [확보한 ERD SQL이 공유된 Slack 글](https://2026-ndc9438.slack.com/archives/C0C3BG88DHR/p1790239227750419)
