from unittest.mock import patch

import httpx
import pytest

from tickets_ui import ticket_request


def test_known_error_keeps_reason_without_upstream_secret(monkeypatch):
    monkeypatch.setenv("DEMO_OPERATOR_TOKEN", "t" * 32)
    response = httpx.Response(503, json={"error": {"code": "LLM_NOT_ENABLED", "message": "secret-key"}})
    with patch("tickets_ui.httpx.request", return_value=response):
        with pytest.raises(RuntimeError) as exc:
            ticket_request("POST", "/v1/ticket-draft-previews", {})
    assert "LLM" in str(exc.value) and "HTTP 503" in str(exc.value)
    assert "secret-key" not in str(exc.value)


def test_unknown_error_never_echoes_raw_response(monkeypatch):
    monkeypatch.setenv("DEMO_OPERATOR_TOKEN", "t" * 32)
    with patch("tickets_ui.httpx.request", return_value=httpx.Response(500, text="password=secret")):
        with pytest.raises(RuntimeError) as exc:
            ticket_request("POST", "/v1/ticket-draft-previews", {})
    assert "HTTP 500" in str(exc.value) and "secret" not in str(exc.value)
