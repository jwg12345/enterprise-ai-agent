import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.agent.ticket_runtime import RunError, SpringLedger

SETTINGS = Settings("http://business", "s" * 32, "v" * 32, "o" * 32)
HEADERS = {"Authorization": "Bearer " + SETTINGS.operator_token, "Idempotency-Key": "same"}
RUN = str(uuid4())
APPROVAL = str(uuid4())
DRAFT = {"incident_id": "INC-014", "title": "점검", "body": "합성", "team": "Platform", "priority": "P1"}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("M3_ENABLED", "false")
    monkeypatch.setenv("M2_ENABLED", "false")
    with TestClient(create_app(SETTINGS, httpx.MockTransport(lambda req: httpx.Response(500)))) as client:
        client.app.state.tickets = AsyncMock()
        client.app.state.tickets.operate.return_value = {"run_id": RUN, "status": "WAITING_APPROVAL"}
        yield client


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/v1/ticket-runs", {"draft": DRAFT}),
    ("GET", "/v1/ticket-runs", None),
    ("GET", "/v1/ticket-runs/" + RUN, None),
    ("POST", f"/v1/ticket-runs/{RUN}/resume", None),
    ("POST", f"/v1/ticket-runs/{RUN}/decisions", {"approval_id": APPROVAL, "decision": "approve"}),
])
def test_viewer_and_unauthenticated_cannot_access_runs(api, method, path, payload):
    assert api.request(method, path, json=payload).status_code == 401
    assert api.request(method, path, json=payload, headers={"Authorization": "Bearer " + SETTINGS.viewer_token,
                       "X-User-Role": "operator", "Idempotency-Key": "same"}).status_code == 403
    api.app.state.tickets.operate.assert_not_called()
    api.app.state.tickets.list_runs.assert_not_called()


def test_creation_uses_authenticated_owner_and_exact_key(api):
    result = api.post("/v1/ticket-runs", headers={**HEADERS, "X-User-ID": "other"}, json={"draft": DRAFT})
    assert result.status_code == 200
    args = api.app.state.tickets.operate.call_args
    assert args.args[0] == "demo-operator"
    assert args.kwargs["key"] == "same"
    assert "run_id" not in args.kwargs


@pytest.mark.parametrize("extra", [{"owner_id": "other"}, {"run_id": RUN}, {"approved": True}])
def test_client_cannot_assign_run_or_approval(api, extra):
    assert api.post("/v1/ticket-runs", headers=HEADERS, json={"draft": DRAFT, **extra}).status_code == 422
    api.app.state.tickets.operate.assert_not_called()


@pytest.mark.parametrize("status,code", [(404, "NOT_FOUND"), (409, "RUN_BUSY"), (409, "IDEMPOTENCY_CONFLICT"), (503, "RECONCILING")])
def test_run_failures_are_preserved(api, status, code):
    api.app.state.tickets.operate.side_effect = RunError(status, code)
    result = api.get("/v1/ticket-runs/" + RUN, headers=HEADERS)
    assert result.status_code == status
    assert result.json()["error"]["code"] == code


def test_database_exception_does_not_leak(api):
    api.app.state.tickets.operate.side_effect = RuntimeError("password=secret")
    result = api.get("/v1/ticket-runs/" + RUN, headers=HEADERS)
    assert result.status_code == 503 and "secret" not in result.text


def test_decision_only_passes_id_and_choice(api):
    result = api.post(f"/v1/ticket-runs/{RUN}/decisions", headers=HEADERS,
                      json={"approval_id": APPROVAL, "decision": "reject"})
    assert result.status_code == 200
    args = api.app.state.tickets.operate.call_args.kwargs
    assert args == {"run_id": RUN, "action": "decision", "approval_id": APPROVAL, "decision": "reject"}


def test_spring_adapter_keeps_server_identity_and_stable_ticket_key():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            assert request.headers["X-User-ID"] == "demo-operator"
            assert request.headers["Authorization"] == "Bearer " + SETTINGS.business_service_token
            assert request.headers["Idempotency-Key"] == "ticket:" + APPROVAL
            return httpx.Response(503, text="secret")
        async with httpx.AsyncClient(base_url="http://business", transport=httpx.MockTransport(handler)) as client:
            ledger = SpringLedger(client, SETTINGS.business_service_token, "demo-operator", "trace")
            with pytest.raises(RunError):
                await ledger.create_ticket(APPROVAL, "a" * 64, "demo-operator", "ticket:" + APPROVAL)
        assert len(calls) == 1
    asyncio.run(run())
