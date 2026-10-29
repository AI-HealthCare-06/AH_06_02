import os
import uuid
import zoneinfo
from dataclasses import field
from enum import StrEnum
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    ENV: Env = Env.LOCAL
    SECRET_KEY: str = f"default-secret-key{uuid.uuid4().hex}"
    TIMEZONE: zoneinfo.ZoneInfo = field(default_factory=lambda: zoneinfo.ZoneInfo("Asia/Seoul"))
    TEMPLATE_DIR: str = os.path.join(Path(__file__).resolve().parent.parent, "templates")

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "pw1234"
    DB_NAME: str = "ai_health"
    DB_CONNECT_TIMEOUT: int = 5
    DB_CONNECTION_POOL_MAXSIZE: int = 10

    COOKIE_DOMAIN: str = ""

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 14 * 24 * 60
    JWT_LEEWAY: int = 5

    # 배포 모델 아티팩트. data/ 는 .gitignore 대상이라 저장소에 올라가지 않는다
    MODEL_ARTIFACT_PATH: str = "data/model/artifact.json"
    # 원문항 기간·음주 코드·후보 적용에 대한 팀 승인 이후에만 켠다.
    D_DIAGNOSED_ALCOHOL_POLICY_ENABLED: bool = False
    # 서빙 artifact 가 가리키는 원본 질환 모델(<실행>/model.joblib·artifact.json)과 background-<질환>.npy 위치
    MODEL_DIR: str = "data/experiment-refit"

    # PHOTO 증빙 비공개 저장소. 로컬 실행 시 쓰기 가능한 별도 경로로 지정한다.
    EVIDENCE_STORAGE_DIR: str = "/app/media/evidence"

    # 예측 큐. PRED-01 이 {prediction_id, job_id} 를 LPUSH 하고 ai_worker 가 BRPOP 한다
    VALKEY_URL: str = "redis://localhost:6379/0"
    PREDICTION_QUEUE_KEY: str = "pred:queue"

    # 질의 챗봇(대화형 추천). 꺼져 있거나 키가 없으면 규칙 추천을 그대로 돌려준다
    CHALLENGE_CHAT_ENABLED: bool = False
    # 키는 저장소 루트 .env(로컬·docker compose) 또는 envs/.prod.env(배포)에만 넣는다.
    # SecretStr 이라 설정 객체를 출력하거나 로그에 남겨도 값이 ********** 로 가려진다
    OPENAI_API_KEY: SecretStr = SecretStr("")
    # challenge_recommendations.llm_model_version 에 저장하므로 32자 이내
    OPENAI_MODEL: str = Field(default="gpt-4o", min_length=1, max_length=32)
    # Responses API 주소. 로컬 E2E 에서 가짜 서버를 붙일 때만 바꾼다
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
