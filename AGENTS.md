# AGENTS.md

당고킬러 저장소에서 코드를 쓰기 전에 읽는 규칙입니다. 사람도 에이전트도 같습니다.

프로젝트 소개는 [README](README.md)에 있습니다.

---

## 시작하기 전에 읽을 것

**화면을 만든다면 반드시 [`docs/design.md`](docs/design.md)를 먼저 읽습니다.**
색·간격·타이포·상태 표현 규칙이 거기 있습니다. 읽지 않고 만들면 팀원 넷의 화면이 제각각이 됩니다.

시각적 기준은 Figma `Hi-Fi v1`입니다. Figma와 `docs/design.md`가 다르면 Figma가 맞습니다. `docs/design.md`를 손으로 고치지 말고 팀에 확인하세요.

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
| A | 배수빈 | `users` |
| B | 홍서윤 | `predictions` · `prediction_contributions` |
| C | 최병주 | `health_records` |
| D | 김이경 | `monsters` · `user_monsters` · `challenges` · `user_challenges` · `challenge_logs` · `challenge_recommendations` · `rewards` · `user_rewards` |

남의 테이블에 직접 쓰지 않습니다. 필요하면 담당자가 제공하는 내부 함수로 요청합니다.
예를 들어 경험치 지급은 D가 `users`를 건드리지 않고 A의 함수를 부릅니다. 레벨 재계산과 레벨업 판정도 A 한 곳에서만 합니다.

---

## 스키마를 바꾸려면

DB 스키마의 원본은 **구글 시트 테이블 명세서**입니다. 저장소 안에 명세서 사본을 만들지 마세요.

순서는 이렇습니다. 시트를 고친다 → 팀에 알린다 → ERD와 DDL을 다시 뽑는다 → 코드를 고친다.

현재 기준은 12테이블 186컬럼 FK 17입니다.

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
- P95가 0이거나 지나치게 작은 factor는 `threat_eligible = false`로 표시하고 위협도 0으로 처리합니다. 임의의 하한값을 넣어 나누지 않습니다. 근거 없이 위협도가 부풀기 때문입니다. 기준 숫자는 모델 1회전 분포를 보고 고정합니다.
- 스파이크처럼 `monsters.default_impact_source`가 `measured`인 캐릭터는 이 계산 밖입니다. 실측 혈당으로 따로 산출합니다.

**direction**

`SHAP > 0`이면 `increase`, `SHAP <= 0`이면 `decrease`로 저장합니다. 0을 decrease에 넣는 건 ENUM에 자리가 없어서지 "위험을 낮춘다"는 뜻이 아닙니다. 위협도 0으로 처리하고, 서비스에서 보호 요인처럼 보여주지 않습니다.

**알아둘 것**

진단 질환 위협도(전역 max 기준)와 미진단 위협도(P95 기준)는 스케일 근거가 다릅니다. 둘 다 0~100이고 같은 `state` 임계값을 쓰지만, 같은 70이 같은 뜻은 아닙니다. 진단자는 예측을 돌리지 않아서 생기는 구조적 차이입니다.

질환별·요인별 원값은 모델 1회전 후 서윤님이 전달합니다.

---

## 어디에 붙이나

- API 추가: `app/apis/v1/` 아래 라우터를 만들고 `app/apis/v1/__init__.py`에 등록
- 테이블 추가: `app/models/`에 Tortoise 모델을 쓰고 `app/db/databases.py`의 `MODELS`에 등록
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
