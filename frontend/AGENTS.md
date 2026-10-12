# AGENTS.md — frontend

Rules for writing screen code under `frontend/`. They apply to humans and
agents alike.

The repository-wide rules are in [`../AGENTS.md`](../AGENTS.md). On any
conflict that file wins and this one only adds frontend-specific detail.
Output language is Korean, as mandated there.

This file is written in English because agents follow English instructions more
reliably. Domain nouns stay in Korean inside backticks (`위협도`, `공략 점수`,
…) so that the vocabulary in the spreadsheets, the database and the UI stays
single-sourced. Do not translate them into new English names.

---

## Building a screen

`docs/prototype/당고킬러-모험시안_v4.html` is the reference. Take colors,
spacing, copy and button shapes from it. Do not invent new ones.

The prototype has three dropdowns left empty with a dashed border: 음주 빈도,
음주량, 외식 빈도. They carry KNHANES codes whose per-value meanings are not
settled yet. Do not fill them in arbitrarily. Note especially that 외식 빈도 runs
backwards — 1 is the most frequent and 7 is almost never.

Support reduced motion. Respect `prefers-reduced-motion` and pause video.

No horizontal scrolling at a 320px viewport width.

---

## Never do this

Do not show a predicted probability for a disease the user has already been
diagnosed with. A user diagnosed with diabetes must never see "당뇨 확률 24%" —
show `진단 관리 중` instead.

토큰은 공통 메모리 세션만 사용한다. localStorage·sessionStorage에 새로 저장하거나
비밀번호·토큰을 콘솔에 출력하지 않는다.

## 공통 구현 연결

실행·담당 페이지·공통 인증·라우팅·API·UI 사용법은 [README.md](README.md)를 따른다.
페이지는 내용 영역만 렌더링하며 공통 헤더와 하단 메뉴를 중복 생성하지 않는다.
개별 페이지에서 별도 토큰 저장소나 API 클라이언트를 만들지 않는다.
날짜·API 활성 상태·봉인 의미는 상위 지침과 실제 서버 응답을 따른다.
API 타임스탬프를 UTC로 가정하지 않는다. KST 달력 날짜는 날짜 그대로 표시한다.
등록되지 않은 화면과 사진 업로드를 완료된 것처럼 표시하지 않는다.
