# 개발 환경과 실행

## 준비물

- Python 3.13 이상
- [uv](https://github.com/astral-sh/uv)
- Docker · Docker Compose

## 설치

```bash
uv sync --group app --group dev
```

API 서버와 테스트에 필요한 것이 `app` · `dev` 그룹에 있습니다. `uv sync`만 하면 기본 의존성만 깔려서 `tortoise`나 `fastapi`를 못 찾습니다.

모델 학습을 한다면 `--group ai`를 더합니다.

## 환경 변수

```bash
cp envs/example.local.env envs/.local.env
cp envs/example.prod.env envs/.prod.env
ln -s envs/.local.env .env
```

실제 값은 `envs/.local.env`에 적고, 저장소 루트의 `.env`는 그 파일을 가리키는 심볼릭 링크로 둡니다. `app/core/config.py`, `docker-compose.yml`, `scripts/ci/run_test.sh` 셋 다 루트의 `.env`를 보기 때문에 링크가 없으면 서버가 안 뜹니다.

`envs/.prod.env`는 배포용이라 로컬에서는 건드리지 않습니다.

값은 각자 환경에 맞게 고치세요. `envs/.local.env`와 `.env`는 커밋되지 않습니다.

## 전체 실행

```bash
docker-compose up -d --build
```

띄우고 나면 화면은 [http://localhost/frontend/](http://localhost/frontend/), Swagger는 [http://localhost/api/docs](http://localhost/api/docs)에서 열립니다.

`port is already allocated`가 나오면 예전에 깔아둔 로컬 MySQL이 포트를 잡고 있는 겁니다.

```bash
sudo lsof -nP -iTCP:3306 -sTCP:LISTEN
```

## 스키마 반영

모델이 바뀐 커밋을 받았다면 마이그레이션을 올립니다.

```bash
uv run aerich upgrade
```

## 처음 DB 준비

처음에는 마이그레이션 → 몬스터·챌린지·보상 시드 → 건강정보 저장 순서로 진행합니다.

```bash
uv run aerich upgrade
uv run python -m scripts.seed.seed_monsters
uv run python -m scripts.seed.seed_challenges
uv run python -m scripts.seed.seed_rewards
```

시드 없이 건강정보를 먼저 저장하면 사용자별 몬스터가 생기지 않아 도감이 미측정으로 남거나 추천이 안 뜰 수 있습니다. 시드를 넣은 뒤 건강정보를 다시 저장하면 새 기록 기준으로 갱신되고, 기존 기록은 지우지 않습니다.

챌린지 마스터를 고쳤을 때도 챌린지 시드를 다시 돌려야 DB에 반영됩니다.

## 개별 실행

```bash
uv run uvicorn app.main:app --reload      # API 서버
uv run --group app --group model --with 'shap==0.50.0' python -m ai_worker.main   # AI 워커
```

워커는 shap 이 lock 에 없어서(`pyproject.toml` model 그룹 주석) 실행할 때 버전을 고정해 붙입니다.
`data/experiment-refit/` 에 `background-diabetes.npy` · `background-hypertension.npy` 가 있어야 합니다.
없으면 워커는 켜져 있어도 예측을 모두 실패로 기록합니다. 두 파일은 모델 폴더(드라이브)에서 받습니다.
