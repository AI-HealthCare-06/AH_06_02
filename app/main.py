from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from app.apis.v1 import v1_routers
from app.core.db.databases import initialize_tortoise
from app.core.exception_handlers import register_exception_handlers

app = FastAPI(
    default_response_class=ORJSONResponse, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json"
)
initialize_tortoise(app)
register_exception_handlers(app)

app.include_router(v1_routers)

# API와 같은 출처에서 D 화면과 공통 모듈을 제공한다.
app.mount(
    "/frontend", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend", html=True), name="frontend"
)
