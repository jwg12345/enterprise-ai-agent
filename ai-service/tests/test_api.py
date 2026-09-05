import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SETTINGS = Settings("http://business", "s" * 32, "v" * 32, "o" * 32)
PARAMS = {"from": "2026-08-01T00:00:00+09:00", "to": "2026-09-01T00:00:00+09:00"}
HEADERS = {"Authorization": "Bearer " + SETTINGS.viewer_token}


def client(handler):
    return TestClient(create_app(SETTINGS, httpx.MockTransport(handler)))


def test_auth_and_identity_not_spoofable():
    def handler(request):
        assert request.headers["X-User-ID"] == "demo-viewer"
        assert request.headers["X-User-Role"] == "viewer"
        assert request.headers["Authorization"] == "Bearer " + SETTINGS.business_service_token
        assert request.headers["X-Request-ID"] == "trace-123"
        return httpx.Response(200, json={"items": [], "page": 0, "size": 20, "total": 0})
    with client(handler) as api:
        assert api.get("/v1/incidents", params=PARAMS).status_code == 401
        result = api.get("/v1/incidents", params=PARAMS,
                         headers={**HEADERS, "X-User-Role": "operator", "X-Request-ID": "trace-123"})
        assert result.status_code == 200
        assert result.headers["X-Request-ID"] == "trace-123"


@pytest.mark.parametrize("change", [
    {"size": 51}, {"page": -1}, {"severity": "P9"}, {"category": "SQL"},
    {"from": "2026-09-02T00:00:00Z"}, {"to": "2028-01-01T00:00:00Z"},
    {"from": "2026-08-01T00:00:00"}, {"unknown": "value"}
])
def test_invalid_query_never_calls_business(change):
    def handler(request):
        pytest.fail("Invalid query reached business API")
    with client(handler) as api:
        assert api.get("/v1/incidents", params={**PARAMS, **change}, headers=HEADERS).status_code == 422


def test_duplicate_query_rejected():
    with client(lambda request: pytest.fail("Duplicate forwarded")) as api:
        assert api.get("/v1/incidents", params=[*PARAMS.items(), ("size", "2"), ("size", "3")],
                       headers=HEADERS).status_code == 422


@pytest.mark.parametrize("failure, expected", [("timeout", 504), ("connection", 502), ("status", 502)])
def test_business_failure_is_not_empty_results(failure, expected):
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret-not-for-response")
        if failure == "connection":
            raise httpx.ConnectError("secret-not-for-response")
        return httpx.Response(503, text="secret-not-for-response")
    with client(handler) as api:
        result = api.get("/v1/incidents", params=PARAMS, headers=HEADERS)
        assert result.status_code == expected
        assert "items" not in result.json()
        assert "secret-not-for-response" not in result.text
        assert len(calls) == 3


def test_readiness_and_liveness_are_separate():
    with client(lambda request: httpx.Response(503)) as api:
        assert api.get("/health/live").status_code == 200
        assert api.get("/health/ready").status_code == 503


def test_bad_upstream_payload_is_rejected():
    with client(lambda request: httpx.Response(200, json={"total": "invalid"})) as api:
        assert api.get("/v1/incidents", params=PARAMS, headers=HEADERS).status_code == 502


def test_missing_and_duplicate_secrets_fail(monkeypatch):
    for key in ("BUSINESS_SERVICE_TOKEN", "DEMO_VIEWER_TOKEN", "DEMO_OPERATOR_TOKEN"):
        monkeypatch.setenv(key, "same" * 8)
    with pytest.raises(RuntimeError):
        Settings.from_env()
