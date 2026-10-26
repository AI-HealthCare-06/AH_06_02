# 대화형 챌린지 추천 — 현재 상태

정리: 2026-10-12

> 2026-10-26 기준 상태와 연결 계약은 [`challenge-rag-contract.md`](challenge-rag-contract.md)를 본다. 아래 "코드는 없다"는 10/12 오전 기준이고, 같은 날 PR #49로 내부 연결 코드(꺼진 상태)가 들어갔다.

## 한 줄

설계와 카드 초안은 10/2 에 나왔고 DB 칸은 10/6 에 팠다. 그 뒤로 구현이 시작되지 않았다.

## 들어 있는 것

| 파일 | 작성 | 내용 |
| --- | --- | --- |
| [rag-plan-20261002.md](rag-plan-20261002.md) | 최병주 · 10/2 | 기획안. MVP 범위, 코퍼스 설계, JSON 출력, 서버 검증, 작업 분담 |
| [challenge-cards-20261002.md](challenge-cards-20261002.md) | 김이경 · 10/2 | 걷기·좌식 상황 카드 12개(C01\~C12), 기존 60개 미션 선택지 재분류, 연결 전 확인 항목 |
| [../../02_team/d-part/d-workpack-20261002.md](../../02_team/d-part/d-workpack-20261002.md) | 김이경 · 10/2 | 6절에 RAG 연결 카드 12개, 8절에 가상 검증 사례 20개 |

둘 다 "승인 전 초안"이라고 명시하고 있다. 두 문서 모두 공유 명세·DB·코드를 바꾸지 않았다고 적혀 있다.

## DB 는 어디까지 갔나

`challenge_recommendations` 에 세 칸이 있다. 10/6 마이그레이션 `4_20261006120121_add_cycles_occurrences_health` 에 들어갔고 `app/models/challenges.py` 에도 있다.

| 컬럼 | 용도 |
| --- | --- |
| `conversation_snapshot` | 질문·답변 기록. 저장 키는 `policy_version` · `fingerprint` · `answers` · `asked` · `card_versions` · `model_version`(예측 모델) · `health_record_id` |
| `llm_model_version` | 후보 선택에 쓴 LLM 식별자. snapshot 의 `model_version` 과 다르다 |
| `evidence_card_ids` | 제안 근거로 전달된 승인 카드 ID 배열. `C01`\~`C12` 고정값 |

대화로 고른 추천도 `source_type` 은 원래 값(`prediction_personal`, `diagnosis_global`)을 유지한다. 대화를 거쳤다는 이유만으로 `conversation` 으로 바꾸지 않으므로, 세 칸은 `source_type` 과 무관하게 채운다 (10/13 A·D 합의).

## 코드는 없다

레포 전체에 RAG, 검색 색인, 카드 파일, 챗봇 엔드포인트가 없다. `api-spec.md` 에 나오는 LLM 언급은 전부 제약 조항이다. "LLM 생성값 불인정", "LLM 이 대상/주기를 바꾸지 않는다" 처럼 LLM 이 결과를 흔들지 못하게 막는 쪽이지 챗봇을 만든다는 내용이 아니다.

pyproject.toml 의 ai 그룹에 sentence-transformers 가 있지만 이건 2026-01-30 부트캠프 템플릿에 torch 와 함께 처음부터 들어 있던 것이고 코드에서 import 하지 않는다.

## 왜 멈췄나

두 문서가 각자 다음 단계를 지목하는데, 그 단계가 비어 있다.

기획안 14절은 "코퍼스·RAG — 담당 1명 지정" 이라고만 적혀 있고 그 한 명이 정해지지 않았다. 15절의 결정 항목 다섯 개도 미결이다.

카드 초안 8절은 "최신 `challenge_master_v1` 기준으로 먼저 허용할 키와 추천 권한 확인" 을 1번으로 둔다. 그 승인이 이뤄지지 않았다.

그리고 두 문서가 레포 밖에만 있어서 어디까지 됐는지 팀에서 보이지 않았다. 이 폴더가 그걸 고치려는 것이다.

## 정할 것

1. 1단계에 넣을지 2단계로 둘지.
2. 1단계에 넣는다면 코퍼스·RAG 담당자는 누구인지.
3. 2단계로 둔다면 세 칸을 테이블명세서에서 2단계로 표시할지.

발표는 2026-11-05 이다. 2단계로 두더라도 설계와 카드 초안이 남아 있으므로, 스키마를 먼저 설계해 둔 범위까지는 산출물로 설명할 수 있다. 구현했다고 말하지 않는다.
