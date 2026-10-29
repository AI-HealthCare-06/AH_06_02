import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.apis.v1 import v1_routers
from app.apis.v1.challenge_chat_routers import chat_setup_issue
from app.core.db.databases import initialize_tortoise
from app.core.exception_handlers import register_exception_handlers

app = FastAPI(
    default_response_class=ORJSONResponse, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json"
)
initialize_tortoise(app)
register_exception_handlers(app)

app.include_router(v1_routers)

# 키가 빠졌거나 스위치가 꺼져 있으면 챗봇이 조용히 규칙 추천으로만 답하므로 시작할 때 한 번 알린다
if issue := chat_setup_issue():
    logging.getLogger(__name__).warning(issue)

# API와 같은 출처에서 D 화면과 공통 모듈을 제공한다.
app.mount(
    "/frontend", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend", html=True), name="frontend"
)
