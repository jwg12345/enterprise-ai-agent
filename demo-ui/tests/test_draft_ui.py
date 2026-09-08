from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"
DRAFT = {"incident_id": "INC-014", "title": "AI 점검 초안", "body": "근거를 검토하세요.", "team": "Platform", "priority": "P1"}
PREVIEW = {"draft": DRAFT, "abstain": False, "citations": [{"document_id": "network", "version": "1",
           "section": "P1", "chunk_id": "c1", "text": "점검 절차"}], "observed_at": "2026-09-06T00:00:00Z"}
FILTERS = {"from": "2026-08-01T00:00:00Z", "to": "2026-09-01T00:00:00Z"}


def prepare(monkeypatch):
    monkeypatch.setenv("M3_ENABLED", "true")
    monkeypatch.setenv("M2_ENABLED", "false")
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["result"] = ({"items": [{"id": "INC-014", "status": "OPEN", "occurred_at": "2026-08-14T00:00:00Z"}],
                                    "total": 1, "page": 0}, "trace", "2026-08-01", "2026-08-31")
    app.session_state["incident_params"] = FILTERS
    return app.run()


def test_preview_requires_separate_registration_and_approval(monkeypatch):
    with patch("tickets_ui.ticket_request", return_value=PREVIEW) as request:
        app = prepare(monkeypatch)
        next(b for b in app.button if b.label == "AI 초안 미리보기").click().run()
        assert not app.exception
        assert request.call_count == 1
        assert request.call_args.args[1] == "/v1/ticket-draft-previews"
        assert request.call_args.args[2]["incident_filters"] == FILTERS
        assert not any(b.label == "승인하고 티켓 생성" for b in app.button)
        request.return_value = {"run_id": "r1", "status": "WAITING_APPROVAL", "ticket_id": None,
                               "approval": {"approval_id": "a1", "draft": DRAFT, "expires_at": "2026-09-07T00:00:00Z"}}
        next(b for b in app.button if b.label == "이 초안으로 승인 요청").click().run()
        assert not app.exception
        assert request.call_count == 2
        assert request.call_args.args[1] == "/v1/ticket-runs"
        assert request.call_args.args[2] == {"draft": DRAFT}
        assert any(b.label == "승인하고 티켓 생성" for b in app.button)


def test_abstention_removes_previous_preview_and_registration(monkeypatch):
    with patch("tickets_ui.ticket_request", return_value=PREVIEW) as request:
        app = prepare(monkeypatch)
        next(b for b in app.button if b.label == "AI 초안 미리보기").click().run()
        request.return_value = {"abstain": True, "draft": None, "citations": []}
        next(b for b in app.button if b.label == "AI 초안 미리보기").click().run()
        assert not app.exception
        assert not any(b.label == "이 초안으로 승인 요청" for b in app.button)
        assert any("보류" in item.value for item in app.info)
