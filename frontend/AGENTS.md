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

The service screen is v5. `docs/prototype/당고킬러-모험시안_v5.html` holds the
markup and styles, and `v5/app.mjs` connects it to the real API. Take colors,
spacing, copy and button shapes from that HTML. Do not invent new ones. The v4
prototype HTML stays only as a historical reference.

Three dropdowns carry KNHANES codes: 음주 빈도, 음주량, 외식 빈도. Their options
in the v5 HTML follow the code meanings in
[`docs/03_ai_data/input-code-map.md`](../docs/03_ai_data/input-code-map.md),
and the app sends the code itself as the value. Keep these lists and that file
in step; do not invent new options.

- 음주 빈도 `alcohol_frequency` 1\~6: 최근 4주 동안 마시지 않음 · 월 1회 미만 ·
  월 1회 정도 · 월 2\~4회 · 주 2\~3회 · 주 4회 이상
- 음주량 `alcohol_amount` 1\~5: 1\~2잔 · 3\~4잔 · 5\~6잔 · 7\~9잔 · 10잔 이상.
  Hidden when 음주 빈도 is 1, and then sent as 0. 10잔 이상 is not an exact count.
- 외식 빈도 `dining_out_freq` 1\~7: 하루 2회 이상 · 하루 1회 · 주 5\~6회 ·
  주 3\~4회 · 주 1\~2회 · 월 1\~3회 · 월 1회 미만. It runs backwards — 1 is the
  most frequent and 7 is almost never.

The screen asks about the last 4 weeks while the KNHANES items ask about the
last year, so the mapping is an approximation. Keep the "최근 4주" wording:
음주 빈도 1 reads "최근 4주 동안 마시지 않음", and both the 음주 and 식생활
sections carry the note "최근 4주 기준으로 선택해 주세요."

Support reduced motion. Respect `prefers-reduced-motion` and pause video.

No horizontal scrolling at a 320px viewport width.

---

## Never do this

Do not show a predicted probability for a disease the user has already been
diagnosed with. A user diagnosed with diabetes must never see "당뇨 확률 24%" —
show `진단 관리 중` instead.

토큰은 공통 메모리 세션만 사용한다. 토큰과 개인정보(비밀번호·건강 수치 등)는
localStorage·sessionStorage에 저장하지 않는다. 새로고침 복원에 필요한 식별자(예: 예측
번호)만 sessionStorage에 둘 수 있다. 비밀번호·토큰을 콘솔에 출력하지 않는다.

## 공통 구현 연결

실행·파일 구성·인증·API 사용법은 [README.md](README.md)를 따른다.
화면 코드는 `v5/app.mjs`에 두고 `shared/auth.mjs`의 세션과 `shared/api.mjs`의 API
클라이언트를 쓴다. 별도 토큰 저장소나 API 클라이언트를 만들지 않는다.
실제 연결 모드에 가상 데이터를 넣지 않는다. 화면만 보는 체험은 `?demo=1`에서 한다.
날짜·API 활성 상태·봉인 의미는 상위 지침과 실제 서버 응답을 따른다.
API 타임스탬프를 UTC로 가정하지 않는다. KST 달력 날짜는 날짜 그대로 표시한다.
등록되지 않은 화면과 사진 업로드를 완료된 것처럼 표시하지 않는다.
