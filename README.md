# 당고킬러 (DangoKiller)

당뇨와 고혈압 위험을 예측하고, 그 위험을 만든 생활습관을 **캐릭터로 바꿔** 하나씩 잡아나가는 서비스입니다.

---

## 기획 이유 

건강검진 결과지는 숫자를 보여주고 끝납니다. "공복혈당 108, 전단계입니다"까지는 말해주지만, 그래서 내일 뭘 해야 하는지는 알려주지 않습니다.

당뇨와 고혈압은 생활습관으로 상당 부분 늦출 수 있는 병인데도, 관리가 지루해서 대부분 3주를 못 넘깁니다.

그래서 관리를 게임으로 바꿨습니다. 다만 게임으로 만들면서 **건강 정보를 왜곡하지 않는 것**을 가장 어려운 제약으로 두었습니다.

---

## 어떻게 동작하는가

**1. 건강정보를 넣으면 위험도가 나옵니다.**
국민건강영양조사(KNHANES) 데이터로 학습한 모델이 당뇨와 고혈압 위험 확률을 각각 계산합니다.

**2. 위험을 만든 요인이 캐릭터가 됩니다.**
SHAP으로 "무엇이 이 확률을 밀어올렸는지"를 구하고, 요인마다 캐릭터를 붙입니다.

| 캐릭터 | 요인 |
| --- | --- |
| 스파이크 | 혈당 |
| 비세라 | 내장지방 · 비만 |
| 코티니 | 흡연 |
| 알데 | 음주 |
| 소디 | 나트륨 · 외식 |

**3. 캐릭터마다 챌린지를 받습니다.**
코티니가 날뛰고 있으면 금연 관련 챌린지가 뜹니다. 하루하루 수행하면 공략 점수가 쌓입니다.

**4. 다시 측정하면 위협도가 움직입니다.**
4주 뒤 건강정보를 다시 넣고 예측을 다시 돌립니다. 그때 캐릭터가 약해집니다.

**5. 조건을 채우면 봉인됩니다.**
최근 28일 중 그 요인 챌린지를 20일 이상 해내고 위협도가 40 아래로 내려가면 봉인. 만성질환에 완치 엔딩은 없으니 처치가 아니라 봉인입니다. 관리를 멈추면 다시 깨어납니다.

---

## 우리가 지킨 세 가지

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
| A | 배수빈 | 회원·인증 · 공통 기반 · ERD · 요구사항 · 문서 총괄 |
| B | 홍서윤 | 예측 모델 · SHAP · 전처리 · 비동기 추론 |
| C | 최병주 | 건강정보 · 대시보드 · 배포 · 인프라 |
| D | 김이경 | 챌린지 · 보상 · 도감 · 와이어프레임 |

한 테이블은 한 사람만 씁니다. 남의 테이블이 필요하면 담당자가 제공하는 함수로 요청합니다.

---

## 기술 스택

| 영역 | 선택 |
| --- | --- |
| API 서버 | FastAPI |
| 추론 | 별도 컨테이너 (`ai_worker`)로 분리 |
| DB | MySQL + Tortoise ORM |
| 캐시·큐 | Valkey |
| 프런트엔드 | React + Vite + Recharts |
| 패키지 | uv |
| 배포 | Docker Compose + EC2 + Nginx + Certbot |

---

## 문서

| 찾는 것 | 보는 곳 |
| --- | --- |
| 제품이 어떻게 동작하는가 | 기획서 |
| 무엇을 만들기로 했는가 | 요구사항 정의서 (67항목) |
| 어떤 테이블에 뭐가 들어가는가 | 테이블 명세서 · ERD (12테이블 186컬럼) |
| 어떤 API를 어떻게 부르는가 | API 명세서 (32개) |
| 색·간격·버튼을 어떻게 쓰는가 | `docs/design.md` |
| 어디에 띄우고 무엇으로 증명하는가 | 배포·검증 계획서 |

문서는 비공개로 팀 드라이브에서 관리합니다. 필요하시면 팀에 요청해주세요.

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

모델 학습을 한다면 `--group ai`를 더합니다. torch가 딸려 와서 무거우니 필요할 때만 받으세요.

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

띄우고 나면 [http://localhost/api/docs](http://localhost/api/docs) 에서 Swagger가 뜹니다.

`port is already allocated`가 나오면 예전에 깔아둔 로컬 MySQL이 포트를 잡고 있는 겁니다.

```bash
sudo lsof -nP -iTCP:3306 -sTCP:LISTEN
```

### 개별 실행

```bash
uv run uvicorn app.main:app --reload      # API 서버
uv run python -m ai_worker.main           # AI 워커
```

---

## 프로젝트 구조

```text
.
├── ai_worker/          # 추론 워커
│   ├── core/           # 설정·로거
│   ├── models/         # 모델 파일
│   ├── tasks/          # 작업 정의
│   └── main.py
├── app/                # FastAPI 서버
│   ├── apis/           # 라우터 (v1)
│   ├── core/           # 설정·DB·JWT·검증
│   ├── dtos/           # 요청·응답 스키마
│   ├── models/         # 테이블 정의
│   ├── services/       # 비즈니스 로직
│   └── main.py
├── docs/               # 설계 문서
├── envs/               # 환경 변수
├── infra/              # Docker·Nginx 설정
├── scripts/            # 배포·CI 스크립트
├── docker-compose.yml
└── pyproject.toml
```

---

## 개발 규칙

**어디에 붙이나**

- API 추가: `app/apis/v1/` 아래 라우터를 만들고 `app/apis/v1/__init__.py`에 등록
- 테이블 추가: `app/models/`에 Tortoise 모델을 쓰고 `app/db/databases.py`의 `MODELS`에 등록
- 추론 로직 추가: `ai_worker/tasks/`에 작성하고 `ai_worker/main.py`에서 호출

**품질 검사**

```bash
docker compose up -d mysql            # 테스트 전에 DB부터
./scripts/ci/run_test.sh              # 테스트
./scripts/ci/code_fommatting.sh       # 포맷 (Ruff)
./scripts/ci/check_mypy.sh            # 타입 (Mypy)
```

테스트는 `pytest`를 직접 부르지 말고 `run_test.sh`로 돌립니다. 이 스크립트가 테스트용 DB를 만들 권한을 먼저 부여한 뒤 pytest를 부릅니다. 직접 부르면 권한 때문에 막힙니다.

**지킬 것**

- 스키마를 바꾸려면 테이블 명세서를 먼저 고치고 팀에 알립니다. ERD와 DDL은 명세서에서 자동 생성됩니다
- UI를 만들기 전에 `docs/design.md`를 읽습니다
- 원시자료와 `.env`는 커밋하지 않습니다
- 커밋 메시지는 `feat:` · `fix:` · `docs:` · `chore:` · `refactor:` · `test:`로 시작합니다

---

## 배포

`scripts/deployment.sh`가 이미지 빌드부터 EC2 컨테이너 실행까지 처리합니다.

```bash
chmod +x scripts/deployment.sh
./scripts/deployment.sh
```

HTTPS는 `scripts/certbot.sh`로 Let's Encrypt 인증서를 받아 적용합니다.

```bash
chmod +x scripts/certbot.sh
./scripts/certbot.sh
```

자세한 절차와 검증 항목은 배포·검증 계획서를 보세요.

---

## 안내

이 서비스는 의료기기가 아닙니다. 진단이나 치료 목적으로 쓸 수 없습니다. 예측 결과는 참고용이며, 건강에 이상이 느껴지면 의료기관을 찾아주세요.