from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.apis.v1 import v1_routers
from app.core.db.databases import initialize_tortoise
from app.core.exception_handlers import register_exception_handlers   # 추가

app = FastAPI(
    default_response_class=ORJSONResponse, docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json"
)
initialize_tortoise(app)
register_exception_handlers(app)                                      # 추가

app.include_router(v1_routers)