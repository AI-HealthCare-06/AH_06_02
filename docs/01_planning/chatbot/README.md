# 대화형 챌린지 추천 (AI·RAG)

정리: 2026-10-26 · 운영 v1.1.3

연결 계약과 지금 상태는 [`challenge-rag-contract.md`](challenge-rag-contract.md)를 먼저 본다. 이 README는 폴더 안내다.

## 지금 상태

- 서버 내부 연결 코드는 있고 꺼져 있다(`enabled=False`). 공개 API와 화면, LLM 설정값(API 키·모델 이름)은 아직 없다.
- 대화형 추천은 1단계 추천 챌린지 21개를 모두 다룬다. 코드마다 선택형 질문 하나, 목표 고정 검사, 승인된 근거 카드가 있다.
- 근거 카드 48장(C01\~C48)은 모두 승인 상태(배수빈, 2026-10-26)다. 출처는 WHO 신체활동·건강한 식사·음주·흡연 팩트시트다.
- 외부 호출 없이 도는 고정 평가 54건이 모두 통과한다. 실제 LLM 응답 평가는 아직 하지 않았다.

## 들어 있는 것

| 파일 | 내용 |
| --- | --- |
| [challenge-rag-contract.md](challenge-rag-contract.md) | 연결 계약. 챌린지 동작, 1단계 범위, AI가 들어올 자리, 연결 전에 정한 것 |
| [cards-20261026.json](cards-20261026.json) | 근거 카드 48장 |
| [golden-cases-20261026.json](golden-cases-20261026.json) | 고정 평가 사례 54건 |
| [evaluation-20261026.json](evaluation-20261026.json) | 평가 결과. `uv run --group app --no-sync python -m scripts.evaluate_rag_preparation`으로 다시 만든다 |
| [rag-plan-20261002.md](rag-plan-20261002.md) | 최병주 · 10/2 기획안. MVP 범위, 코퍼스 설계, 서버 검증 |
| [challenge-cards-20261002.md](challenge-cards-20261002.md) | 김이경 · 10/2 카드 초안. 연결 전 확인 항목(8절)은 계약 문서 4절에서 정했다 |

## 코드

| 파일 | 하는 일 |
| --- | --- |
| `app/services/conversation_recommendations.py` | 규칙 후보를 받아 질문·검색·선택·검증·저장 |
| `app/services/rag_cards.py` | 지원 코드, 질문, 카드 검색, 선택 검증 |
| `app/services/rag_provider.py` | LLM 선택 인터페이스와 OpenAI 어댑터 |
| `scripts/evaluate_rag_preparation.py` | 고정 평가 실행 |

## 지나온 일

- 10/2: 기획안과 카드 초안 12장이 나왔다.
- 10/6: `challenge_recommendations`에 대화 기록용 칸 세 개(`conversation_snapshot` · `llm_model_version` · `evidence_card_ids`)를 만들었다.
- 10/12: 내부 연결 코드가 들어갔다(PR #49). 지원 코드는 걷기·좌식 3개, 카드는 모두 draft였다.
- 10/26: 1단계 추천 챌린지를 21개로 늘리고, 대화형 추천이 21개를 모두 다루도록 질문·목표 검사·카드를 갖춰 승인했다(PR #75).
