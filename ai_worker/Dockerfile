FROM python:3.13-slim

WORKDIR /app

# 1. uv 설치 (공식 이미지에서 복사해오는 가장 깔끔한 방법)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 2. 의존성 패키지 관리 파일을 컨테이너 내부에 복사합니다.
COPY pyproject.toml uv.lock ./

# 3. 워커는 app 모델·설정(DB)과 model 그룹(pandas·scikit-learn·joblib)을 함께 쓴다.
#    shap 은 lock 에 넣을 수 없어(pyproject.toml model 그룹 주석) 같은 버전으로 따로 설치한다.
#    asyncmy 등 C 확장은 빌드 도구가 필요하다
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --group ai --group app --group model --no-dev --frozen \
    && uv pip install --python /app/.venv/bin/python 'shap==0.50.0'

# 4. 워커는 app 패키지(ORM 모델·설정·D 위협도 갱신)를 import 한다.
COPY ./app ./app
COPY ./ai_worker ./ai_worker

# 5. uv run 은 lock 기준으로 다시 동기화해 shap 을 지울 수 있어 venv 의 python 을 바로 쓴다.
#    모델(experiment-refit/)·서빙 artifact(data/model/)는 이미지에 넣지 않고 compose 볼륨으로 붙인다.
CMD ["/app/.venv/bin/python", "-m", "ai_worker.main"]
