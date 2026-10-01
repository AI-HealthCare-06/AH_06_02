# docs

## 원본이 어디인지

| 문서 | 원본 | 이 폴더의 파일 |
| --- | --- | --- |
| 요구사항 | 구글 시트 `당고킬러_요구사항정의서` | `01_planning/requirements.md` |
| 테이블 | 구글 시트 `당고킬러_테이블명세서` | `01_planning/table-spec.md` |
| API | 구글 시트 `당고킬러_API 명세서` | `01_planning/api-spec.md` |
| 화면 | Figma | `02_team/design.md` |
| 구현 규칙 | 이 저장소 | `../AGENTS.md` |

**구글 시트가 원본입니다.** 이 폴더의 마크다운은 사본이고, 코드를 쓸 때 읽기 위한 것입니다.

바꿀 때는 시트를 먼저 고치고 팀에 알린 뒤 사본을 다시 뽑습니다. 사본만 고치면 문서가 갈라집니다.

## 이 폴더가 왜 있는가

명세가 구글 시트에만 있으면 코드를 쓸 때마다 사람이 복붙해서 넘겨야 합니다. 스무 개 넘는 API를 그렇게 하면 중간에 빠지는 게 생깁니다.

저장소 안에 두면 `docs/01_planning/`을 읽고 `AGENTS.md` 규칙대로 만들라고 한 줄로 지시할 수 있습니다.

## 사본 갱신

문서별 항목 수는 각 원본 시트를 기준으로 확인한다. 2026-10-01 현재 B 예측 API는 지정 B 탭에 확정된 예측 접수·상태/결과 조회·기여도 조회 3개다. 전체 테이블·API·요구사항 수는 원본 시트에서 확인하며 이 README에는 오래된 집계를 복제하지 않는다.

## 데이터 문서 상태

`03_ai_data/data.md` — KNHANES 출처, 라이선스 확인 항목, 코드북 대조, 전처리 규칙, 표본 수와 데이터 한계를 기록합니다. raw data와 개인별 결과는 ignored `data/`에만 둡니다. `NFR-MODL-003` · `NFR-MODL-005` · `NFR-MODL-006`은 이 파일을 지목합니다.

## B 예측·모델 문서

- `01_planning/api-predictions.md` — 지정 B API 시트와 대조한 예측 API 3개 계약
- `model.md` — X/y 정의와 혈압·혈당 제외 사유를 빠르게 찾는 모델 입력 요약
- `03_ai_data/model.md` — X/y 정의, 전역 중요도와 위협도 산식, 내부 호출 계약
- `03_ai_data/input-code-map.md` — KNHANES 원 코드와 서비스 입력값 매핑
- `03_ai_data/data.md` — KNHANES 자료원 및 전처리 현황
- `03_ai_data/experiment.md` — 실제 24조합 탐색 1회전의 조건과 결과·제한
- `03_ai_data/verification.md` — 전처리·계약 테스트와 검증 범위
- `03_ai_data/submission-status.md` — B 제출 항목, 완료 상태와 외부 의존성
