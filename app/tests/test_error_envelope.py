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


def test_every_code_has_status_and_message() -> None:
    assert len(list(ErrorCode)) == 27
    missing = [code for code in ErrorCode if code not in ERROR_SPEC]
    assert missing == []
    for code, (status, message) in ERROR_SPEC.items():
        assert 400 <= status <= 599, code
        assert message.strip(), code


def test_success_response_uses_envelope(client: TestClient) -> None:
    res = client.get("/ok")
    assert res.status_code == 200
    assert res.json() == {"success": True, "data": {"available": True}}


def test_app_error_keeps_code_and_status(client: TestClient) -> None:
    res = client.get("/duplicated")
    assert res.status_code == 409
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AUTH_EMAIL_DUPLICATED"


def test_extra_fields_are_included(client: TestClient) -> None:
    res = client.get("/weak")
    assert res.status_code == 422
    assert res.json()["error"]["unmet"] == ["min_length"]


def test_legacy_http_exception_is_wrapped(client: TestClient) -> None:
    res = client.get("/legacy")
    assert res.status_code == 401
    body = res.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "Authenticate Failed" not in body["error"]["message"]


def test_validation_error_reports_fields(client: TestClient) -> None:
    res = client.post("/signup", json={"email": "a", "age": "abc"})
    assert res.status_code == 400
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["fields"][0]["field"] == "age"


def test_unknown_path_keeps_envelope(client: TestClient) -> None:
    res = client.get("/no-such-path")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_unhandled_error_hides_internals(client: TestClient) -> None:
    res = client.get("/boom")
    assert res.status_code == 500
    body = res.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "의도적인 오류" not in body["error"]["message"]


def test_detail_key_is_never_used(client: TestClient) -> None:
    for path in ("/duplicated", "/legacy", "/boom", "/no-such-path"):
        assert "detail" not in client.get(path).json()
