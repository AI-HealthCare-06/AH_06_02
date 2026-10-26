# AGENTS.md

Rules to read before writing code in the 당고킬러 (DangoKiller) repository.
They apply to humans and agents alike.

The project overview is in [README](README.md). Typing, style and architecture
rules are in [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md). On any conflict the
precedence is: `pyproject.toml` settings > SYSTEM_DESIGN.md > this document.

This file is written in English because agents follow English instructions more
reliably. Everything the agent *produces* is Korean — see Output Language below.
Domain nouns stay in Korean inside backticks (`위협도`, `공략 점수`, …) so that
the vocabulary in the spreadsheets, the database and the UI stays single-sourced.
Do not translate them into new English names.

---

## Read this first

**If you are building a screen, read the v5 HTML and
[`docs/02_team/design.md`](docs/02_team/design.md) before anything else.** Skip
them and the four of us ship four different-looking screens.

The visual source of truth is the v5 HTML,
[`frontend/docs/prototype/당고킬러-모험시안_v5.html`](frontend/docs/prototype/당고킬러-모험시안_v5.html),
which is also the service screen (the team switched from v4 on 2026-10-20).
Take colors, spacing, typography and copy from it. `docs/02_team/design.md`
adds the meaning, state representation and implementation rules the HTML does
not show; parts of it still describe v4 until the team updates it. When the two
disagree, v5 wins. Do not hand-edit design.md; ask the team instead. How the
frontend is laid out and run is in [`frontend/README.md`](frontend/README.md).

---

## Output Language (MANDATORY)

ALL output MUST be in Korean — code comments, docstrings, commit messages,
documentation, log and error messages you author, and chat responses.
Only identifiers (variable / function / class / test names) and language
keywords remain in English.

---

## Workflow — plan.md and Canon TDD

The work queue is `plan.md` at the repository root. Put the task list and the
test list there and cross items off one at a time.

`plan.md` is **not under version control** (it is in `.gitignore`). NEVER
mention it in commit messages, PR titles or bodies, code comments, docstrings,
test names, or any generated file. Read it and follow it, but leave no trace of
it in the output.

One test at a time, red → green → refactor:

1. Pick the next unmarked item in `plan.md`. If a new scenario appears while you
   work, do not implement it — add it to `plan.md` as an unmarked item.
2. Turn that item into exactly one failing test with a behavior-describing name
   (for example `test_same_day_restart_excludes_recognized_occurrences`).
   Confirm it fails for the expected reason.
3. Write the simplest code that makes the new test and every existing test pass.
   Never copy a computed actual value into an expected value — derive the
   expectation independently.
4. Refactor only while green, one named refactoring at a time, running tests
   after each step.
5. Repeat until the feature is complete.

When fixing a defect: write a failing test at the API level first, then the
smallest test that reproduces the problem, then make both pass.

The order of work is: plan → AI review → implement → review against the plan →
E2E (Claude in Chrome).

---

## Tidy First — never mix structural and behavioral change

Every change is exactly one of:

- **Structural**: rearranging code without changing behavior (rename, extract, move).
- **Behavioral**: adding or modifying functionality.

Never put both in one commit. When both are needed, make the structural change
first and run the tests before and after to prove behavior did not move.

---

## Import rules

- All imports go at the top of the file. Never import inside a function.
- Order: standard library → third-party → local modules.
- The only exception is a `TYPE_CHECKING` block used to break a circular import,
  for type hints only.

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some_module import SomeClass  # type hints only
```

- Test files follow the same rules.

---

## Vocabulary — three values that must never be mixed

This is the most frequent mistake in this project.

| Term | What it is | When it changes | Where it lives |
| --- | --- | --- | --- |
| `위험도` (disease risk) | probability of developing the disease, 0\~1, produced by the model | only on re-prediction | `predictions.dm_probability` · `htn_probability` |
| `위협도` (factor threat) | how much that factor pushed `위험도` up, 0\~100 | only on re-prediction | `user_monsters.impact_score` |
| `공략 점수` (weekly attack score) | how much of this week's challenge the user has done | immediately, on each challenge log | `user_monsters.weekly_progress` |

**Completing a challenge changes neither `위험도` nor `위협도`.** It raises only
`공략 점수`. The first two move only when the user submits health data again and
a new prediction runs.

Never render `공략 점수` as a percentage. The weekly goal of 100 is a fixed
display target, not a cap on the stored value.

The old terms `HP` and `주간 데미지` were dropped on 2026-09-28. Fix them wherever
they still appear in code or docs.

---

## Ownership boundaries — one table, one owner

| Part | Owner | Tables |
| --- | --- | --- |
| A | 배수빈 | `users` |
| B | (vacant) | 홍서윤 left on 2026-10-07. `predictions` · `prediction_contributions` moved to C |
| C | 최병주 | `health_records` · `predictions` · `prediction_contributions` |
| D | 김이경 | `monsters` · `user_monsters` · `challenges` · `user_challenges` · `user_challenge_occurrences` · `user_attack_cycles` · `challenge_logs` · `challenge_recommendations` · `rewards` · `user_rewards` |

Never write to someone else's table directly. Call the internal function its
owner provides. Granting XP, for example, is D calling A's function rather than
touching `users`. Level recalculation and level-up detection happen in A only.

---

## Changing the schema

The database is what the Tortoise models and the migrations in
`app/core/db/migrations` say it is. With two people on the team the Google Sheet
테이블 명세서 (table specification) is a record, not a gate: there is no
approval step before coding.

The order is: change the model → write the migration → change the code →
bring the sheet up to date → regenerate the copies with
`uv run scripts/sync_specs.py`.

The copies live in [`docs/01_planning`](docs/01_planning).
[`erd.md`](docs/01_planning/erd.md) is the diagram and
[`erd.sql`](docs/01_planning/erd.sql) is the DDL reference. Do not hand-edit
them; the next sync overwrites them. When a copy and the migrations disagree,
the migrations describe the database.

One person runs migrations. Duplicate numbers conflict at merge time, so check
the last number on `main` before creating a new one.

The sheet currently lists 17 tables and 252 columns.

---

## Time zone

DATETIME values are stored as KST (Asia/Seoul) naive. `TORTOISE_ORM` sets
`timezone: Asia/Seoul`, `use_tz` is off, and application code consistently uses
`datetime.now(config.TIMEZONE)`. This is a single-time-zone service, so nothing
is converted to UTC on the way in.

`start_date` · `end_date` · `scheduled_date` · `progress_week_start` ·
`log_date` are KST calendar dates and are stored as DATE. Do not convert them to
UTC and shift the day.

API response formatting is a separate matter. Follow the common rules in the
spreadsheet.

---

## `공략 사이클` (attack cycle) — one character at a time

Settled on 2026-10-04.

One cycle attacks exactly one character. Never split the three challenge slots
across several characters. Split them and `공략 점수` accumulates at a third of
the speed per character, so no `봉인` (seal) is ever reached before the 28 days
are up.

| Item | Rule |
| --- | --- |
| Target selection | the highest `위협도` is picked automatically. The user can change it from the `도감` (monster book) — REQ-RECO-006 |
| Target stability | a re-measurement during the cycle does not switch the target automatically |
| Duration | challenges in the same cycle all end together at the D28 boundary regardless of when they were added. Nothing carries over — REQ-CHLG-011 |
| Intake | up to 2 at the start, 1 more per cycle from week 2, 3 concurrent at most — REQ-CHLG-002 |
| Storage | one row in `user_attack_cycles`. Missions and recommendations reference it by `cycle_id` |

The cycle number `cycle_week` and the "currently targeted" flag `is_target` are
not stored; they are computed at read time. The weekly `공략 점수` resets on the
calendar week boundary (Monday 00:00 KST), which is not the same as the cycle
week. Do not mix the two.

The completion rate is the number of recognized-complete scheduled occurrences
divided by the number of scheduled occurrences. Scheduled occurrences are
created ahead of time in `user_challenge_occurrences`, one per date and slot.
`skipped` occurrences and expired unlogged ones do not count toward the
numerator but stay in the denominator.

Phase 1 does not judge habit formation. `habit_established` NULL means not
evaluated; do not read FALSE as "not formed". Keep the terminal status name
`graduated` as it is, but display it as "기간 종료" (period ended) on screen.

---

## Data

The training data is the Korea National Health and Nutrition Examination Survey
(KNHANES) from the KDCA. **The raw files are covered by a confidentiality
undertaking and must never be committed.**

Keep raw files in `data/`. `.gitignore` blocks `data/` · `*.sav` ·
`*.sas7bdat`. Run `git status` once before committing.

Once a file is committed, deleting it later leaves it in history. Undoing that
means rewriting history and every teammate re-cloning.

`.env` files and `SECRET_KEY` are never committed either. Only
`envs/example.*.env` belong in the repository.

---

## Model

Blood pressure and blood glucose are excluded from the model inputs because
those values were used to define the labels. Including them raises accuracy but
makes the prediction a tautology. Do not put them back.

Because of that, `spike` (스파이크, the blood-glucose character) is the one
character with no SHAP contribution available, so its `위협도` is derived
separately from the measured glucose collected in precision mode.

### Computing `위협도`

SHAP values are used in two distinct ways. Do not mix them.

- Per-user contribution: signed SHAP. Never take the absolute value.
- Global importance: `mean(|SHAP|)`. An average of absolute values, so always
  non-negative.

Both reference values live in the **model artifact metadata**, not in the
database. They are metadata bound to a `model_version`, so pinning them to the
model file is safer. `ai_worker` loads the values for that `model_version` and
computes from them. The metadata holds three things: `global_importance_max` per
disease, `positive_shap_p95` per disease × factor, and `threat_eligible` per
factor.

**Global score (diagnosed disease)**

`normalized_score = (that factor's mean|SHAP| / global_importance_max) × 100`

- Diabetes factors are computed among diabetes factors, hypertension among
  hypertension. Never across diseases.
- `mean|SHAP|` is always non-negative, so no negative clipping is needed.
- `위협도` for a diagnosed disease = `normalized_score × behavior_weight`

**Personal threat (undiagnosed disease)**

`positive_shap = max(signed SHAP, 0)`

`threat_score = min(100, positive_shap / positive_shap_p95 × 100)`

- `positive_shap_p95` is the P95 of the positive-SHAP distribution per
  disease × factor, taken from the reference population of that `model_version`.
  It is not a per-disease max. The global max expresses relative importance
  between factors, so using it as a personal scale would mean something else.
- SHAP contributions are stored as `DECIMAL(8,5)`. In the model metadata, a
  `positive_shap_p95 < 0.00001` is below the stored precision and is marked
  `threat_eligible = false`. A factor with fewer than 400 positive SHAP samples
  is also marked false, because the top 5% behind a P95 would then rest on fewer
  than 20 expected observations. Only factors that clear both checks are true.
  These thresholds exist for estimability and storage precision; they carry no
  clinical meaning. Revisit them if the contribution format or the P95 sampling
  changes.
- Characters whose `monsters.default_impact_source` is `measured` — `spike` is
  the one today — are outside this calculation and are derived from measured
  glucose instead.

**direction**

Store `increase` when `SHAP > 0` and `decrease` when `SHAP <= 0`. Putting zero
into `decrease` is only because the ENUM has no third slot; it does not mean
"lowers the risk". Treat it as `위협도` 0 and never present it to the user as a
protective factor.

**Worth knowing**

`위협도` for a diagnosed disease (scaled by the global max) and for an
undiagnosed one (scaled by P95) rest on different bases. Both are 0\~100 and both
use the same `state` thresholds, but 70 in one does not mean 70 in the other.
The gap is structural: diagnosed users never run a prediction.

---

## Project structure

```text
.
├── ai_worker/          # inference worker
│   ├── core/           # settings, logger
│   ├── schemas/        # job schemas
│   ├── tasks/          # job definitions
│   ├── model_contract.py
│   └── main.py
├── app/                # FastAPI server
│   ├── apis/           # routers (v1)
│   ├── core/           # settings, DB, migrations, JWT, validators
│   ├── dtos/           # request and response schemas
│   ├── models/         # table definitions
│   ├── repositories/   # queries
│   ├── services/       # business rules
│   └── main.py
├── data/               # model artifacts and raw data (never committed)
├── docs/               # design documents, including SYSTEM_DESIGN.md
├── envs/               # environment variables
├── frontend/           # v5 service screen (HTML + JS modules)
├── infra/              # Docker and Nginx configuration
├── scripts/            # deploy, CI, seed and sync scripts
├── tests/              # model contract and script tests
├── docker-compose.yml
└── pyproject.toml
```

---

## Where to put things

- New API: add a router under `app/apis/v1/` and register it in
  `app/apis/v1/__init__.py`.
- New table: write the Tortoise model in `app/models/` and register it in
  `TORTOISE_APP_MODELS` in `app/core/db/databases.py`.
- New inference logic: write it in `ai_worker/tasks/` and call it from
  `ai_worker/main.py`.
- Nothing new goes at the repository root. Documents go in `docs/`, scripts in
  `scripts/`, infrastructure config in `infra/`. Only files a tool looks for at
  the root stay there. `scripts/ci/check_root_files.py` enforces this in
  pre-commit and GitHub Actions; extend its allowlist only for such a tool file.

Inference and SHAP computation happen in `ai_worker` only. Running them inside
`app` breaks the 3-second P95 response budget. `app` enqueues the job and
returns 202 with a `job_id`.

---

## Error responses

Use the error codes in `ErrorCode` (`app/core/errors.py`), 27 today, mirrored in
the `에러 코드` (error codes) tab of the API specification sheet. Reuse an
existing code whenever one fits. If none does, add the new code to `ErrorCode`
in the same change, mention it in the PR, and update the sheet tab afterwards.
Never return an error code that is not in `ErrorCode`.

---

## Commits and PRs

- Documentation and configuration changes may go straight to `main`. Code goes
  on a `feature/` branch and comes in through a PR.
- Commit messages start with `feat:` · `fix:` · `docs:` · `chore:` ·
  `refactor:` · `test:`.
- One logical change per commit. Commit only when every test passes and no
  linter warning remains.
- State in the first line of the body whether the change is structural or
  behavioral (Tidy First).
- Run the checks before pushing.

```bash
docker compose up -d mysql            # the DB first
./scripts/ci/run_test.sh              # tests
./scripts/ci/code_fommatting.sh       # format (Ruff)
./scripts/ci/check_mypy.sh            # types (Mypy)
```

Never call `pytest` directly. `run_test.sh` grants the privilege to create the
test database first and then calls pytest; calling it directly fails on
permissions.

Installing `pre-commit` runs format and lint automatically at commit time.

```bash
uv run pre-commit install
```

Two things differ from the mentor's shared rules. The commit prefixes stay
`feat:` · `fix:` and so on rather than `structural:` · `behavioral:`, because the
PR template and every PR merged so far use that scheme; structural versus
behavioral is recorded in the first line of the body instead. Tests run through
`run_test.sh` rather than `uv run pytest` for the reason in the paragraph above.

---

## Never

- Never phrase anything to the user as a diagnosis ("you have diabetes"). Show
  probabilities only.
- Never deduct points or reset a streak because the user missed a day.
- Never subtract `공략 점수` from `위협도` directly.
- Never store a password in plain text or write one to the log.
