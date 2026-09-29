"""공통 에러 봉투 회귀 테스트.

에러 응답이 `success / data / error` 형식에서 벗어나면 여기서 잡힌다.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ERROR_SPEC, AppError, ErrorCode
from app.core.exception_handlers import register_exception_handlers
from app.dtos.envelope import ok


class _SignUpBody(BaseModel):
    email: str
    age: int


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/ok")
    def _ok() -> dict[str, object]:
        return ok({"available": True})

    @app.get("/duplicated")
    def _duplicated() -> None:
        raise AppError(ErrorCode.AUTH_EMAIL_DUPLICATED)

    @app.get("/weak")
    def _weak() -> None:
        raise AppError(ErrorCode.AUTH_WEAK_PASSWORD, extra={"unmet": ["min_length"]})

    @app.get("/legacy")
    def _legacy() -> None:
        raise HTTPException(status_code=401, detail="Authenticate Failed.")

    @app.post("/signup")
    def _signup(body: _SignUpBody) -> dict[str, object]:
        return ok({"id": 1})

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("의도적인 오류")

    return TestClient(app, raise_server_exceptions=False)


def test_모든_코드에_상태와_메시지가_있다() -> None:
    assert len(list(ErrorCode)) == 27
    missing = [code for code in ErrorCode if code not in ERROR_SPEC]
    assert missing == []
    for code, (status, message) in ERROR_SPEC.items():
        assert 400 <= status <= 599, code
        assert message.strip(), code


def test_성공응답은_success_data_형식이다(client: TestClient) -> None:
    res = client.get("/ok")
    assert res.status_code == 200
    assert res.json() == {"success": True, "data": {"available": True}}


def test_app_error는_코드와_상태를_따라간다(client: TestClient) -> None:
    res = client.get("/duplicated")
    assert res.status_code == 409
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AUTH_EMAIL_DUPLICATED"


def test_부가필드를_함께_내려준다(client: TestClient) -> None:
    res = client.get("/weak")
    assert res.status_code == 422
    assert res.json()["error"]["unmet"] == ["min_length"]


def test_기존_http_exception도_봉투에_맞춘다(client: TestClient) -> None:
    res = client.get("/legacy")
    assert res.status_code == 401
    body = res.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "Authenticate Failed" not in body["error"]["message"]


def test_검증실패는_틀린_필드를_알려준다(client: TestClient) -> None:
    res = client.post("/signup", json={"email": "a", "age": "abc"})
    assert res.status_code == 400
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["fields"][0]["field"] == "age"


def test_없는_경로도_봉투를_지킨다(client: TestClient) -> None:
    res = client.get("/그런거없음")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_예상못한_예외는_내부사정을_숨긴다(client: TestClient) -> None:
    res = client.get("/boom")
    assert res.status_code == 500
    body = res.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "의도적인 오류" not in body["error"]["message"]


def test_detail_키는_쓰지_않는다(client: TestClient) -> None:
    for path in ("/duplicated", "/legacy", "/boom", "/그런거없음"):
        assert "detail" not in client.get(path).json()
