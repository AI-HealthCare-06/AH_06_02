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

## The mistake everyone makes — three different numbers

This service has three numbers with different meanings. Mixing them makes the
screen lie to the user.

**`위험도`** — the probability of developing the disease. The API returns
`dm_probability` and `htn_probability` as decimals between 0 and 1. Convert to a
percentage for display, e.g. `24%`.

**`위협도`** — how much that factor pushed the user's `위험도` up. The field is
`impact_score`, an integer from 0 to 100. **It is not a percentage.** Render
`72`, never `72%`. When the value is absent the state is `미측정` and the screen
shows `—`.

**`공략 점수`** — how much of this week's challenge work is done. The field is
`weekly_progress`; the weekly target is fixed at 100. Render `40 / 100`, never
as a percentage. It resets to 0 at Monday 00:00 KST.

Completing a challenge does not move `위협도`. It only raises `공략 점수`.
`위협도` changes only when the user re-enters health data and the prediction
runs again.

---

## API

Paths start with `/api/v1`. Auth is a JWT bearer token: access tokens last 30
minutes, refresh tokens 14 days. Only signup, login, token refresh and the email
duplicate check are callable without a token.

Every response has one of these two shapes:

```json
{ "success": true, "data": { } }
{ "success": false, "error": { "code": "AUTH_EMAIL_DUPLICATED", "message": "이미 가입된 이메일입니다" } }
```

Lists arrive as a `data.items` array. Paging is `?page=1&size=20`.

`error.message` is a Korean sentence that is safe to show to the user as-is. Do
not invent your own copy in the frontend — render it directly. Branch on
`error.code` when you need to behave differently.

JSON keys are snake_case. Timestamps arrive as ISO 8601 UTC; convert to KST in
the frontend.

---

## Endpoints that exist today

As of 2026-10-12 five routers are registered and 27 endpoints are callable.

```
auth         GET  /auth/check-email            POST /auth/signup
             POST /auth/login                  POST /auth/refresh
             POST /auth/logout

users        GET  /users/me                    PATCH /users/me
             PATCH /users/me/diagnosis         PATCH /users/me/password
             DELETE /users/me                  GET /users/me/level

health       POST /health-records              GET  /health-records
             GET  /dashboard/summary           GET  /dashboard/trends

challenges   POST /challenge-recommendations/generate
             GET  /challenge-recommendations
             PATCH /challenge-recommendations/{id}
             PATCH /challenge-recommendations/{id}/unsuppress
             POST /user-challenges             GET  /user-challenges
             POST /user-challenges/{id}/logs   GET  /user-challenges/{id}/logs
             GET  /monsters/me

predictions  POST /predictions                 GET /predictions/{id}
             GET  /predictions/{id}/contributions
```

Rewards and the full `도감` screens are specified but not callable yet. When you
build those screens, mock them using the exact response shapes in
`docs/01_planning/api-spec.md` at the repository root (predictions are in
`api-predictions.md`), and keep every call in one place so the mocks are easy to
swap out later.

This list goes stale. Check `app/apis/v1/__init__.py` when it matters.

---

## Monsters

The codes are `spike`, `alde`, `cotinine`, `viscera`, `sodi`. In Korean:
스파이크, 알데, 코티니, 비세라, 소디.

`spike` derives its `위협도` from a measured blood glucose value. If the user
does not enter fasting glucose in precise mode it stays `미측정`. The other four
come from model contributions.

`sodi` is on hold. All five exist in the `도감` definition, but the current
database seed has four, `sodi` produces a `위협도` for hypertension only, and it
is excluded from automatic challenge recommendation candidates.

---

## The seven 도감 states

| value | label | condition |
| --- | --- | --- |
| rage | 매우 주의 | `위협도` 70 or above |
| caution | 주의 | 40 or above, below 70 |
| stable | 안정 | above 0, below 40 |
| not_contributing | 현재 기여 없음 | `위협도` is 0 and there is no resolution record |
| resolved | 요인 해소됨 | `위협도` is 0 and a resolution record exists |
| sealed | 봉인 완료 | the 28-day `공략` condition was met |
| unmeasured | 미측정 | no value |

Whether a `위협도` of 0 means `현재 기여 없음` or `요인 해소됨` depends on
whether a resolution record exists. Never decide it from the number alone.

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

Do not write copy that asserts a medical diagnosis or treatment. Do not remove
the "for reference only" notice from any result screen.

Do not show a predicted probability for a disease the user has already been
diagnosed with. A user diagnosed with diabetes must never see "당뇨 확률 24%" —
show `진단 관리 중` instead.

Do not keep tokens in `localStorage` in plaintext for long. Never log passwords
or tokens to the console.

KNHANES raw data never enters this repository. It is covered by a
security undertaking (`보안서약`).
