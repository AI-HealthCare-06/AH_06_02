# AGENTS.md

당고킬러 저장소에서 코드를 쓰기 전에 읽는 규칙입니다. 사람도 에이전트도 같습니다.

프로젝트 소개는 [README](README.md)에 있습니다.

---

## 시작하기 전에 읽을 것

**화면을 만든다면 반드시 [`docs/02_team/design.md`](docs/02_team/design.md)를 먼저 읽습니다.**
색·간격·타이포·상태 표현 규칙이 거기 있습니다. 읽지 않고 만들면 팀원 넷의 화면이 제각각이 됩니다.

시각적 기준은 Figma `Hi-Fi v1`입니다. Figma와 `docs/02_team/design.md`가 다르면 Figma가 맞습니다. 이 파일을 손으로 고치지 말고 팀에 확인하세요.

---

## 용어 — 세 값을 섞지 않습니다

이 프로젝트에서 가장 자주 나는 실수입니다.

| 이름 | 무엇인가 | 언제 바뀌나 | 어디에 |
| --- | --- | --- | --- |
| 위험도 | 모델이 낸 질환 발생 확률 (0~1) | 재예측할 때 | `predictions.dm_probability` · `htn_probability` |
| 위협도 | 그 요인이 위험도를 얼마나 밀어올렸는가 (0~100) | 재예측할 때 | `user_monsters.impact_score` |
| 공략 점수 | 이번 주 챌린지를 얼마나 했는가 | 챌린지 수행 즉시 | `user_monsters.weekly_progress` |

**챌린지를 수행해도 위험도와 위협도는 안 바뀝니다.** 공략 점수만 오릅니다. 건강정보를 다시 넣고 예측을 다시 돌려야 앞의 둘이 움직입니다.

공략 점수는 퍼센트로 표기하지 않습니다. 주간 목표 100은 화면 표시용 고정값입니다.

옛 용어 `HP`와 `주간 데미지`는 2026-09-28에 폐기했습니다. 코드나 문서에서 보이면 고쳐주세요.

---

## 소유 경계 — 한 테이블은 한 사람만 씁니다

| 파트 | 담당 | 테이블 |
| --- | --- | --- |
| A | 배수빈 | `users` · `predictions` · `prediction_contributions` |
| B | (공석) | 2026-10-03 홍서윤 이탈. `predictions` · `prediction_contributions` 는 A가 맡습니다 |
| C | 최병주 | `health_records` |
| D | 김이경 | `monsters` · `user_monsters` · `challenges` · `user_challenges` · `user_challenge_occurrences` · `user_attack_cycles` · `challenge_logs` · `challenge_recommendations` · `rewards` · `user_rewards` |

남의 테이블에 직접 쓰지 않습니다. 필요하면 담당자가 제공하는 내부 함수로 요청합니다.
예를 들어 경험치 지급은 D가 `users`를 건드리지 않고 A의 함수를 부릅니다. 레벨 재계산과 레벨업 판정도 A 한 곳에서만 합니다.

---

## 스키마를 바꾸려면

DB 스키마의 원본은 **구글 시트 테이블 명세서**입니다. 저장소 안의 사본을 손으로 고치지 마세요.

순서는 이렇습니다. 시트를 고친다 → 팀에 알린다 → ERD와 DDL을 다시 뽑는다 → migration을 쓴다 → 코드를 고친다.

사본은 [`docs/01_planning`](docs/01_planning)에 있습니다. [`erd.md`](docs/01_planning/erd.md)가 다이어그램, [`erd.sql`](docs/01_planning/erd.sql)이 DDL 기준입니다. 시트와 사본이 다르면 시트가 맞습니다. 사본은 `uv run scripts/sync_specs.py`로 다시 뽑습니다.

migration은 한 사람이 돌립니다. 번호가 겹치면 머지할 때 충돌하니, 새로 만들기 전에 main에 올라온 마지막 번호를 확인하세요.

현재 기준은 14테이블 222컬럼 FK 23입니다. 실제 DB에 걸린 FK는 그중 일부입니다. `health_records` · `user_attack_cycles` · `user_challenge_occurrences` 가 들어온 뒤 한 번에 겁니다.

---

## 시간대

DATETIME은 KST(Asia/Seoul) naive로 저장합니다. `TORTOISE_ORM` 이 `timezone: Asia/Seoul` 이고 `use_tz` 를 켜지 않았으며, 앱 코드도 `datetime.now(config.TIMEZONE)` 으로 통일되어 있습니다. 단일 시간대 서비스라 저장 단계에서 UTC로 변환하지 않습니다.

`start_date` · `end_date` · `scheduled_date` · `progress_week_start` · `log_date` 는 KST 달력 날짜라 DATE로 저장합니다. UTC로 변환해 하루를 밀지 않습니다.

API 응답 표기는 별도입니다. 시트의 공통 규칙을 따르세요.

---

## 공략 사이클 — 한 번에 한 캐릭터

2026-10-04 확정입니다.

한 주기 동안 캐릭터 하나만 공략합니다. 챌린지 슬롯 3개를 여러 캐릭터에 나누지 않습니다. 나누면 공략 점수가 캐릭터마다 3분의 1 속도로 쌓여서 28일이 끝나도 봉인이 생기지 않습니다.

| 항목 | 기준 |
| --- | --- |
| 대상 선정 | 위협도 1순위 자동 선정. 사용자가 도감에서 변경 가능 (REQ-RECO-006) |
| 대상 고정 | 주기 중에는 재측정 결과로 자동 변경하지 않습니다 |
| 기간 | 같은 주기의 챌린지는 투입 시점과 관계없이 D28 경계에서 함께 끝납니다. 이월 없음 (REQ-CHLG-011) |
| 투입 | 초기 최대 2개. 2주차부터 주기당 1개 추가. 동시 최대 3개 (REQ-CHLG-002) |
| 저장 | `user_attack_cycles` 한 행. 미션과 추천은 `cycle_id` 로 참조합니다 |

주기 번호 `cycle_week` 와 공략 중 여부 `is_target` 은 저장하지 않고 조회할 때 계산합니다. 주간 공략 점수는 월요일 0시 KST에 초기화되는 달력 주 기준이라 주기 주차와 다릅니다. 섞지 마세요.

수행률은 인정 완료한 예정 기회 수를 예정 기회 수로 나눈 값입니다. 예정 기회는 `user_challenge_occurrences` 에 날짜와 슬롯 단위로 미리 만들어둡니다. `skipped` 와 기한이 지난 미기록은 분자에 넣지 않고 분모에는 남깁니다.

1단계에서는 습관 졸업을 판정하지 않습니다. `habit_established` 는 NULL이 미평가이고 FALSE를 미형성으로 읽지 않습니다. 종료 상태명 `graduated` 는 그대로 두되 화면에는 "기간 종료"로 표시합니다.

---

## 데이터

학습 데이터는 질병관리청 국민건강영양조사(KNHANES)입니다. **원시자료는 보안서약 대상이라 저장소에 올리지 않습니다.**

원시자료는 `data/` 폴더에 두세요. `.gitignore`가 `data/` · `*.sav` · `*.sas7bdat`을 막고 있습니다. 커밋 전에 `git status`로 한 번 확인하세요.

한 번 커밋되면 파일을 지워도 히스토리에 남습니다. 되돌리려면 히스토리를 다시 쓰고 팀원 전원이 다시 받아야 합니다.

`.env` 파일과 `SECRET_KEY`도 올리지 않습니다. `envs/example.*.env`만 저장소에 둡니다.

---

## 모델

혈압과 혈당은 모델 입력에서 뺐습니다. 이 값들이 라벨을 정의하는 데 쓰였기 때문입니다. 넣으면 정확도는 올라가지만 동어반복이 됩니다. 되살리지 마세요.

이것 때문에 스파이크(혈당)만 SHAP 기여도를 구할 수 없어서, 정밀 모드에서 받은 실측 혈당으로 위협도를 따로 산출합니다.

### 위협도 계산

SHAP 값을 두 가지로 나눠 씁니다. 섞지 마세요.

- 개인별 기여도: signed SHAP. 절댓값을 쓰지 않습니다.
- 전역 중요도: `mean(|SHAP|)`. 절댓값 평균이라 항상 0 이상입니다.

두 기준값은 DB가 아니라 **모델 아티팩트 메타데이터**에 둡니다. `model_version`에 종속된 모델 메타데이터라 모델 파일과 함께 버전이 고정되는 편이 안전합니다. `ai_worker`가 해당 `model_version`의 값을 불러 계산합니다. 메타데이터에 들어가는 것은 질환별 `global_importance_max`, 질환 × factor별 `positive_shap_p95`, factor별 `threat_eligible` 세 가지입니다.

**전역 점수 (진단 질환)**

`normalized_score = (해당 요인의 mean|SHAP| / global_importance_max) × 100`

- 당뇨 요인끼리, 고혈압 요인끼리 따로 계산합니다. 질환을 섞지 않습니다.
- `mean|SHAP|`은 항상 0 이상이라 음수 클립이 필요 없습니다.
- 진단 질환 위협도 = `normalized_score × behavior_weight`

**개인 위협도 (미진단 질환)**

`positive_shap = max(signed SHAP, 0)`

`threat_score = min(100, positive_shap / positive_shap_p95 × 100)`

- `positive_shap_p95`는 해당 `model_version`의 reference population에서 뽑은 질환 × factor별 positive SHAP 분포의 P95입니다. 질환별 max가 아닙니다. 전역 max는 요인 간 상대 중요도라서 개인 스케일 기준으로 쓰면 의미가 달라집니다.
- 현재 SHAP contribution 저장 정밀도는 `DECIMAL(8,5)`입니다. model metadata에서는 `positive_shap_p95 < 0.00001`이면 저장 정밀도보다 작으므로 `threat_eligible = false`로 처리합니다. 또한 양수 SHAP 표본이 400개 미만이면 P95 상위 5%를 뒷받침하는 기대 관측치가 20개 미만이므로 false로 처리합니다. 두 기준을 모두 통과한 factor만 true입니다. 이 기준은 추정 가능성과 저장 정밀도를 위한 운영 기준이며 임상적 의미는 없습니다. contribution 형식이나 P95 산출 표본이 바뀌면 다시 검토합니다.
- 스파이크처럼 `monsters.default_impact_source`가 `measured`인 캐릭터는 이 계산 밖입니다. 실측 혈당으로 따로 산출합니다.

**direction**

`SHAP > 0`이면 `increase`, `SHAP <= 0`이면 `decrease`로 저장합니다. 0을 decrease에 넣는 건 ENUM에 자리가 없어서지 "위험을 낮춘다"는 뜻이 아닙니다. 위협도 0으로 처리하고, 서비스에서 보호 요인처럼 보여주지 않습니다.

**알아둘 것**

진단 질환 위협도(전역 max 기준)와 미진단 위협도(P95 기준)는 스케일 근거가 다릅니다. 둘 다 0~100이고 같은 `state` 임계값을 쓰지만, 같은 70이 같은 뜻은 아닙니다. 진단자는 예측을 돌리지 않아서 생기는 구조적 차이입니다.

질환별·요인별 원값은 모델 1회전 후 서윤님이 전달합니다.

---

## 어디에 붙이나

- API 추가: `app/apis/v1/` 아래 라우터를 만들고 `app/apis/v1/__init__.py`에 등록
- 테이블 추가: `app/models/`에 Tortoise 모델을 쓰고 `app/core/db/databases.py`의 `TORTOISE_APP_MODELS`에 등록
- 추론 로직 추가: `ai_worker/tasks/`에 작성하고 `ai_worker/main.py`에서 호출

추론과 SHAP 계산은 `ai_worker`에서만 합니다. `app`에서 직접 돌리면 응답 P95 3초를 못 지킵니다. `app`은 큐에 넣고 `job_id`와 함께 202를 반환합니다.

---

## 에러 응답

에러 코드는 API 명세서 `에러 코드` 탭의 27개를 씁니다. 새 코드가 필요하면 시트에 먼저 등록하고 팀에 알린 뒤 씁니다. 코드를 임의로 만들지 마세요.

---

## 커밋과 PR

- 문서와 설정 변경은 `main`에 바로 밀어도 됩니다. 코드는 `feature/` 브랜치를 파서 PR로 올립니다
- 커밋 메시지는 `feat:` · `fix:` · `docs:` · `chore:` · `refactor:` · `test:`로 시작합니다
- 커밋 하나에 기능 하나
- 올리기 전에 검사를 돌립니다

```bash
./scripts/ci/run_test.sh
./scripts/ci/code_fommatting.sh
./scripts/ci/check_mypy.sh
```

---

## 하지 말 것

- 사용자에게 "당뇨입니다" 같은 진단 표현을 쓰지 않습니다. 확률만 보여줍니다
- 챌린지를 못 한 날에 감점하거나 연속 기록을 초기화하지 않습니다
- 공략 점수를 위협도에서 직접 빼지 않습니다
- 비밀번호를 평문으로 저장하거나 로그에 남기지 않습니다
