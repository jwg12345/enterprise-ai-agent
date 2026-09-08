import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SETTINGS = Settings("http://business", "s" * 32, "v" * 32, "o" * 32)
OPERATOR = {"Authorization": "Bearer " + SETTINGS.operator_token}
APPROVAL_ID = str(uuid4())
DRAFT = {"incident_id": "INC-1", "title": "점검", "body": "합성 본문", "team": "Platform", "priority": "P1"}
PROPOSAL = {"run_id": str(uuid4()), "proposal_version": 1, "draft": DRAFT}
APPROVAL = {**PROPOSAL, "approval_id": APPROVAL_ID, "owner_id": "demo-operator",
            "draft_hash": "a" * 64, "status": "PENDING", "expires_at": "2026-09-07T00:00:00Z", "ticket_id": None}
TICKET_REQUEST = {"approval_id": APPROVAL_ID, "draft_hash": "a" * 64}
TICKET = {"id": str(uuid4()), "approval_id": APPROVAL_ID, **DRAFT,
          "status": "OPEN", "created_at": "2026-09-06T00:00:00Z"}


def client(handler):
    return TestClient(create_app(SETTINGS, httpx.MockTransport(handler)))


@pytest.mark.parametrize("path,payload", [
    ("/v1/approvals", PROPOSAL),
    (f"/v1/approvals/{APPROVAL_ID}/decision", {"decision": "approve"}),
    ("/v1/tickets", TICKET_REQUEST),
])
def test_writes_require_authenticated_operator(path, payload):
    with client(lambda req: pytest.fail("Unauthorized write forwarded")) as api:
        assert api.post(path, json=payload).status_code == 401
        assert api.post(path, json=payload, headers={
            "Authorization": "Bearer " + SETTINGS.viewer_token, "X-User-Role": "operator",
            "Idempotency-Key": "same",
        }).status_code == 403


def test_identity_and_trace_are_server_controlled():
    def handler(request):
        assert request.headers["X-User-ID"] == "demo-operator"
        assert request.headers["X-User-Role"] == "operator"
        assert request.headers["Authorization"] == "Bearer " + SETTINGS.business_service_token
        assert request.headers["X-Request-ID"] == "trace-1"
        assert json.loads(request.content) == PROPOSAL
        return httpx.Response(201, json=APPROVAL)
    with client(handler) as api:
        result = api.post("/v1/approvals", json=PROPOSAL, headers={
            **OPERATOR, "X-User-ID": "other", "X-User-Role": "viewer", "X-Request-ID": "trace-1"})
        assert result.status_code == 201
        assert result.json()["status"] == "PENDING"


@pytest.mark.parametrize("payload", [
    {"decision": "auto-approve"}, {"decision": "approve", "owner_id": "other"},
    {"decision": "approve", "draft": DRAFT},
])
def test_decision_cannot_carry_identity_or_changed_draft(payload):
    with client(lambda req: pytest.fail("Invalid decision forwarded")) as api:
        assert api.post(f"/v1/approvals/{APPROVAL_ID}/decision", json=payload, headers=OPERATOR).status_code == 422


def test_ticket_key_required_and_body_cannot_override_ledger():
    with client(lambda req: pytest.fail("Invalid ticket forwarded")) as api:
        assert api.post("/v1/tickets", json=TICKET_REQUEST, headers=OPERATOR).status_code == 422
        assert api.post("/v1/tickets", json={**TICKET_REQUEST, "title": "changed"},
                        headers={**OPERATOR, "Idempotency-Key": "same"}).status_code == 422


@pytest.mark.parametrize("status", [200, 201])
def test_ticket_retry_preserves_key_and_status(status):
    def handler(request):
        assert request.headers["Idempotency-Key"] == "same"
        assert json.loads(request.content) == TICKET_REQUEST
        return httpx.Response(status, json=TICKET)
    with client(handler) as api:
        result = api.post("/v1/tickets", json=TICKET_REQUEST, headers={**OPERATOR, "Idempotency-Key": "same"})
        assert result.status_code == status
        assert result.json()["id"] == TICKET["id"]


@pytest.mark.parametrize("status,code", [(403, "FORBIDDEN"), (404, "NOT_FOUND"), (409, "APPROVAL_EXPIRED")])
def test_business_rejection_preserved_without_internal_message(status, code):
    with client(lambda req: httpx.Response(status, json={"error": {"code": code, "message": "secret"}})) as api:
        result = api.get(f"/v1/approvals/{APPROVAL_ID}", headers=OPERATOR)
        assert result.status_code == status
        assert result.json()["error"]["code"] == code
        assert "secret" not in result.text


def test_timeout_never_automatically_repeats_write():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret")
    with client(handler) as api:
        result = api.post("/v1/tickets", json=TICKET_REQUEST, headers={**OPERATOR, "Idempotency-Key": "same"})
        assert result.status_code == 504
        assert len(calls) == 1
        assert "secret" not in result.text


@pytest.mark.parametrize("payload", [{"secret": "raw"}, {**APPROVAL, "owner_id": "other"}])
def test_invalid_or_wrong_owner_response_rejected(payload):
    with client(lambda req: httpx.Response(200, json=payload)) as api:
        result = api.get(f"/v1/approvals/{APPROVAL_ID}", headers=OPERATOR)
        assert result.status_code == 502
        assert "raw" not in result.text
