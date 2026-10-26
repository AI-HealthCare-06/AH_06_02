# 당고킬러 (DangoKiller)

당뇨와 고혈압 위험을 예측하고, 그 위험을 **몬스터로 바꿔** 건강 챌린지를 수행하며 생활습관을 하나씩 잡아나가는 서비스입니다.

## 바로 써 보기

**http://13.125.130.94**

주소로 들어가면 서비스 첫 화면(`/frontend/`)으로 넘어갑니다. 가입하고 건강정보를 넣으면 실제 모델이 위험도를 계산합니다. 아직 https가 아니라서 평소 쓰는 비밀번호는 넣지 마세요.

가입 없이 화면만 둘러보려면 [체험 모드](http://13.125.130.94/frontend/?demo=1)로 들어갑니다. 체험 모드에서 넣은 값은 서버에 저장되지 않습니다.

---

## 기획 이유

건강검진 결과지는 숫자를 보여주고 끝납니다. "공복혈당 108, 전단계입니다"까지는 말해주지만, 그래서 내일 뭘 해야 하는지는 알려주지 않습니다.

당뇨와 고혈압은 생활습관으로 상당 부분 늦출 수 있는 병인데도, 관리가 지루해서 대부분 3주를 못 넘깁니다.

그래서 관리를 게임으로 바꿨습니다. 다만 게임으로 만들면서 **건강 정보를 왜곡하지 않는 것**을 가장 어려운 제약으로 두었습니다.

---

## 동작 방법

**1. 건강정보를 넣으면 위험도가 나옵니다.**
국민건강영양조사(KNHANES) 데이터로 학습한 모델이 당뇨와 고혈압 위험 확률을 각각 계산합니다.

**2. 위험을 만든 요인이 캐릭터가 됩니다.**
SHAP으로 "무엇이 이 확률을 밀어올렸는지"를 구하고, 요인마다 캐릭터를 붙입니다.

| 캐릭터 | 요인 |
| --- | --- |
| 스파이크 | 혈당 |
| 알데 | 음주 |
| 코티니 | 흡연 |
| 비세라 | 내장지방 · 비만 · 활동 부족 |

**3. 가장 위협적인 캐릭터부터 챌린지로 공략합니다.**
위협도가 가장 높은 캐릭터 하나를 28일 동안 공략합니다. 코티니가 날뛰고 있으면 금연 관련 챌린지가 뜹니다. 하루하루 수행하면 공략 점수가 쌓이고, 수행을 인정받을 때마다 보상 카드 5장 중 1장을 골라 모험가와 방을 꾸밉니다. 중복으로 얻은 아이템은 성장의 조각이 되고, 조각을 모으면 성장 아이템이 3단계까지 자랍니다.

**4. 다시 측정하면 위협도가 움직입니다.**
4주 뒤 건강정보를 다시 넣으면 예측을 다시 돌립니다. 그 요인이 줄었다면 그때 캐릭터가 약해집니다.

**5. 조건을 채우면 봉인됩니다.**
최근 28일 중 그 요인 챌린지를 20일 이상 해내고 위협도가 40 아래로 내려가면 봉인. 만성질환에 완치 엔딩은 없으니 처치가 아니라 봉인입니다. 관리를 멈추면 다시 깨어납니다. 지금(1단계)은 봉인 판정을 하지 않고, 28일이 지나면 "기간 종료"로 보여줍니다.

---

## RULE

**겁주지 않습니다.** 확률은 보여주되 진단하지 않습니다. "당뇨입니다"라고 말하지 않습니다.

**거짓말하지 않습니다.** 챌린지를 한 번 했다고 질환 위험이 실제로 줄지는 않습니다. 그래서 즉시 반응하는 값과 실제 위험도를 분리했습니다.

| 이름 | 무엇인가 | 언제 바뀌나 |
| --- | --- | --- |
| 위험도 | 모델이 낸 질환 발생 확률 | 재예측할 때 |
| 위협도 | 그 요인이 위험도를 얼마나 밀어올렸는가 (0~100) | 재예측할 때 |
| 공략 점수 | 이번 주 챌린지를 얼마나 했는가 | 수행 즉시 |

구현은 복잡해졌지만 이건 양보하지 않았습니다.

**실패를 벌하지 않습니다.** 못 한 날은 아무 일도 일어나지 않습니다. 감점도 연속 기록 초기화도 없습니다.

---

## 팀

| 파트 | 이름 | 맡은 것 |
| --- | --- | --- |
| A | 배수빈 | 회원·인증 · 공통 기반 · ERD · 요구사항 · 문서 총괄 · 배포 |
| B | 홍서윤 | 예측 모델 · SHAP · 전처리 (2026-10-07 퇴소) |
| C | 최병주 | 건강정보 · 대시보드 · 예측 API · 예측 워커 · 인프라 |
| D | 김이경 | 챌린지 · 보상 · 도감 · 위협도 · 와이어프레임 (2026-10-16 퇴소, D 후속은 배수빈) |

---

## 기술 스택

| 영역 | 선택 |
| --- | --- |
| API 서버 | FastAPI |
| 추론 | 별도 컨테이너 (`ai_worker`)로 분리 |
| DB | MySQL + Tortoise ORM |
| 캐시·큐 | Valkey |
| 프런트엔드 | HTML + JavaScript 모듈 (빌드 없음, FastAPI가 `/frontend/`로 제공) |
| 패키지 | uv |
| 배포 | Docker Compose + EC2 + Nginx. main에 머지하면 GitHub Actions가 자동 배포 |

---

## 문서

| 찾는 것 | 보는 곳 |
| --- | --- |
| 무엇을 만들기로 했는가 | `docs/01_planning/requirements.md` (77항목) |
| 어떤 테이블에 뭐가 들어가는가 | `docs/01_planning/table-spec.md` (17테이블 252컬럼) |
| 테이블이 어떻게 엮이는가 | `docs/01_planning/erd.md` · `erd.sql` |
| 어떤 API를 어떻게 부르는가 | `docs/01_planning/api-spec.md` (43개) |
| 예측 API 상세 계약 | `docs/01_planning/api-predictions.md` |
| 모델 입력·SHAP·서비스 계약 | `docs/03_ai_data/model.md` |
| 색·간격·버튼을 어떻게 쓰는가 | `docs/02_team/design.md` |
| 서비스 화면(v5)의 연결 범위와 보상 규칙 | `docs/02_team/prototype-v5-proposal.md` |
| 프론트 파일 구성과 실행 | `frontend/README.md` |

요구사항 정의서와 테이블 명세서, API 명세서는 구글 시트가 원본입니다. 레포의 세 파일은 `uv run scripts/sync_specs.py`로 뽑은 사본이라 손으로 고치지 않습니다. 시트를 먼저 고치고 다시 뽑습니다.

기획서와 배포·검증 계획서는 팀 드라이브에만 있습니다. 필요하시면 팀에 요청해주세요.

`docs/README.md`에 원본이 어디인지 정리돼 있습니다.

---

## 데이터

학습 데이터는 질병관리청 국민건강영양조사입니다.

**원시자료는 저장소에 올리지 않습니다.** 보안서약 대상이라 `data/` · `*.sav` · `*.sas7bdat`을 `.gitignore`로 막아뒀습니다. 전처리 결과와 모델 파일만 공유합니다.

혈압과 혈당은 모델 입력에서 뺐습니다. 이 값들이 라벨을 정의하는 데 쓰였기 때문입니다. 넣으면 정확도는 올라가지만 "혈당이 높으니 당뇨 위험이 높다"는 동어반복이 됩니다.

---

## 실행

### 준비물

- Python 3.13 이상
- [uv](https://github.com/astral-sh/uv)
- Docker · Docker Compose

### 설치

```bash
uv sync --group app --group dev
```

API 서버와 테스트에 필요한 것이 `app` · `dev` 그룹에 있습니다. `uv sync`만 하면 기본 의존성만 깔려서 `tortoise`나 `fastapi`를 못 찾습니다.

모델 학습을 한다면 `--group ai`를 더합니다.

### 환경 변수

```bash
cp envs/example.local.env envs/.local.env
cp envs/example.prod.env envs/.prod.env
ln -s envs/.local.env .env
```

실제 값은 `envs/.local.env`에 적고, 저장소 루트의 `.env`는 그 파일을 가리키는 심볼릭 링크로 둡니다. `app/core/config.py`, `docker-compose.yml`, `scripts/ci/run_test.sh` 셋 다 루트의 `.env`를 보기 때문에 링크가 없으면 서버가 안 뜹니다.

`envs/.prod.env`는 배포용이라 로컬에서는 건드리지 않습니다.

값은 각자 환경에 맞게 고치세요. `envs/.local.env`와 `.env`는 커밋되지 않습니다.

### 전체 실행

```bash
docker-compose up -d --build
```

띄우고 나면 화면은 [http://localhost/frontend/](http://localhost/frontend/), Swagger는 [http://localhost/api/docs](http://localhost/api/docs)에서 열립니다.

`port is already allocated`가 나오면 예전에 깔아둔 로컬 MySQL이 포트를 잡고 있는 겁니다.

```bash
sudo lsof -nP -iTCP:3306 -sTCP:LISTEN
```

### 스키마 반영

모델이 바뀐 커밋을 받았다면 마이그레이션을 올립니다.

```bash
uv run aerich upgrade
```

### 처음 DB 준비

처음에는 마이그레이션 → 몬스터·챌린지·보상 시드 → 건강정보 저장 순서로 진행합니다.

```bash
uv run aerich upgrade
uv run python -m scripts.seed.seed_monsters
uv run python -m scripts.seed.seed_challenges
uv run python -m scripts.seed.seed_rewards
```

시드 없이 건강정보를 먼저 저장하면 사용자별 몬스터가 생기지 않아 도감이 미측정으로 남거나 추천이 안 뜰 수 있습니다. 시드를 넣은 뒤 건강정보를 다시 저장하면 새 기록 기준으로 갱신되고, 기존 기록은 지우지 않습니다.

챌린지 마스터를 고쳤을 때도 챌린지 시드를 다시 돌려야 DB에 반영됩니다.

### 개별 실행

```bash
uv run uvicorn app.main:app --reload      # API 서버
uv run --group app --group model --with 'shap==0.50.0' python -m ai_worker.main   # AI 워커
```

워커는 shap 이 lock 에 없어서(`pyproject.toml` model 그룹 주석) 실행할 때 버전을 고정해 붙입니다.
`data/experiment-refit/` 에 `background-diabetes.npy` · `background-hypertension.npy` 가 있어야 합니다.
없으면 워커는 켜져 있어도 예측을 모두 실패로 기록합니다. 두 파일은 모델 폴더(드라이브)에서 받습니다.

---

## 코드를 쓰기 전에

라우터·모델·워커를 어디에 붙이는지, 품질 검사를 어떻게 돌리는지, 커밋과 PR 규칙은 [AGENTS.md](AGENTS.md)에 있습니다. 사람도 에이전트도 같은 문서를 봅니다.

---

## 배포

평소 배포는 자동입니다. 서버에서 도는 코드(`app/` · `ai_worker/` · `frontend/` · `scripts/` · 의존성 · 마스터 CSV)가 바뀐 PR이 main에 머지되면 GitHub Actions(`.github/workflows/deploy.yml`)가 앱·워커 이미지를 `v1.1.N`(N은 실행 번호)으로 빌드해 올리고, 서버에서 마이그레이션 → 재시작 → 상태 확인 → 시드까지 진행합니다. 상태 확인에 실패하면 이전 버전으로 되돌립니다. 머지부터 반영까지 5~10분 걸립니다.

- 문서만 바뀐 머지는 배포하지 않습니다.
- 다시 배포하려면 Actions 탭 → deploy → Run workflow에서 main을 고릅니다.
- 진행 상황은 Actions 탭의 deploy에서, 서버 기록은 `~/deploy.log`에서 봅니다.
- 서버 쪽 스크립트는 `infra/deploy/server-deploy.sh`입니다. 서버에는 `/home/ubuntu/deploy.sh`로 직접 설치돼 있어서, 이 파일을 고치면 서버 사본도 같이 바꿔야 합니다.
- `docker-compose.prod.yml`, nginx 설정, `.prod.env`, 모델 파일은 자동 배포 대상이 아닙니다. 바뀔 때만 아래 수동 절차를 씁니다.

아래 수동 배포는 비상용입니다. 수동 스크립트는 로컬 `envs/.prod.env`를 서버에 덮어쓰므로, 그 전에 `APP_VERSION` · `AI_WORKER_VERSION`을 지금 운영 중인 버전과 맞춥니다.

`scripts/deployment.sh`가 이미지 빌드·푸시와 EC2의 앱·워커 컨테이너 실행을 처리하고, HTTPS는 `scripts/certbot.sh`로 Let's Encrypt 인증서를 받아 적용합니다. 둘 다 `chmod +x` 한 번 해두고 실행하면 됩니다. 자세한 절차와 검증 항목은 배포·검증 계획서를 보세요.

`deployment.sh`는 아이디와 토큰을 물어보는 대화형 스크립트라 터미널에서 직접 실행합니다. 마이그레이션과 시드는 하지 않으니 끝난 뒤 서버의 `~/project`에서 따로 돌립니다.

```bash
docker compose up -d mysql nginx    # 첫 배포 때만. 스크립트는 고른 서비스만 올립니다
docker compose exec fastapi uv run --no-sync aerich upgrade
docker compose exec fastapi uv run --no-sync python -m scripts.seed.seed_monsters   # seed_challenges · seed_rewards도 같은 방식
```

스크립트가 로컬의 `infra/nginx/prod_http.conf`에서 `server_name`을 서버 IP로 바꿔 두므로, 배포 뒤에는 `git checkout infra/nginx/prod_http.conf`로 되돌립니다.

---

## 안내

이 서비스는 의료기기가 아닙니다. 진단이나 치료 목적으로 쓸 수 없습니다. 예측 결과는 참고용이며, 건강에 이상이 느껴지면 의료기관을 찾아주세요.
