import os
import uuid
import zoneinfo
from dataclasses import field
from enum import StrEnum
from pathlib import Path

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
<<<<<<< HEAD
    # 원문항 기간·음주 코드·후보 적용에 대한 팀 승인 이후에만 켠다.
    D_DIAGNOSED_ALCOHOL_POLICY_ENABLED: bool = False
=======
    # 서빙 artifact 가 가리키는 원본 질환 모델(<실행>/model.joblib·artifact.json)과 background-<질환>.npy 위치
    MODEL_DIR: str = "experiment-refit"

    # 예측 큐. PRED-01 이 {prediction_id, job_id} 를 LPUSH 하고 ai_worker 가 BRPOP 한다
    VALKEY_URL: str = "valkey://localhost:6379/0"
    PREDICTION_QUEUE_KEY: str = "pred:queue"
>>>>>>> 49281e0 (feat(worker): 예측 큐·워커 연결)
