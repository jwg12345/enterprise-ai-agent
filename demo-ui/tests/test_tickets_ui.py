from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"
RUN = {"run_id": "run-1", "status": "WAITING_APPROVAL", "ticket_id": None,
       "approval": {"approval_id": "approval-1", "draft": {"incident_id": "INC-014", "title": "합성 점검",
                      "body": "본문", "team": "Platform", "priority": "P1"}, "expires_at": "2026-09-07T00:00:00Z"}}


def test_register_does_not_auto_approve_and_button_sends_only_decision(monkeypatch):
    monkeypatch.setenv("M3_ENABLED", "true")
    monkeypatch.setenv("M2_ENABLED", "false")
    with patch("tickets_ui.ticket_request", return_value=RUN) as request:
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        next(b for b in app.button if b.label == "초안 등록 · 승인 대기").click().run()
        assert not app.exception
        assert request.call_count == 1
        assert request.call_args.args[1] == "/v1/ticket-runs"
        request.return_value = {**RUN, "status": "COMPLETED", "ticket_id": "ticket-1"}
        next(b for b in app.button if b.label == "승인하고 티켓 생성").click().run()
        assert not app.exception
        assert request.call_args.args[2] == {"approval_id": "approval-1", "decision": "approve"}
        assert any("ticket-1" in item.value for item in app.success)
        assert not any(b.label == "승인하고 티켓 생성" for b in app.button)


def test_unknown_result_is_error_and_does_not_show_ticket(monkeypatch):
    monkeypatch.setenv("M3_ENABLED", "true")
    monkeypatch.setenv("M2_ENABLED", "false")
    with patch("tickets_ui.ticket_request", side_effect=RuntimeError("결과 확인 필요")):
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        next(b for b in app.button if b.label == "초안 등록 · 승인 대기").click().run()
        assert not app.exception
        assert any("결과 확인 필요" in item.value for item in app.error)
        assert not app.success


def test_reject_removes_approval_actions_and_never_displays_ticket(monkeypatch):
    monkeypatch.setenv("M3_ENABLED", "true")
    monkeypatch.setenv("M2_ENABLED", "false")
    with patch("tickets_ui.ticket_request", return_value=RUN) as request:
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        next(b for b in app.button if b.label == "초안 등록 · 승인 대기").click().run()
        request.return_value = {**RUN, "status": "REJECTED"}
        next(b for b in app.button if b.label == "거절").click().run()
        assert not app.exception
        assert request.call_args.args[2] == {"approval_id": "approval-1", "decision": "reject"}
        assert any("거절됨" in item.value for item in app.markdown)
        assert not any(b.label in {"승인하고 티켓 생성", "거절", "저장된 실행 재개"} for b in app.button)
        assert not app.success


def test_restored_expired_run_has_no_write_actions(monkeypatch):
    monkeypatch.setenv("M3_ENABLED", "true")
    monkeypatch.setenv("M2_ENABLED", "false")
    with patch("tickets_ui.ticket_request") as request:
        request.return_value = {"items": [{"run_id": "run-1"}]}
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        next(b for b in app.button if b.label == "최근 실행 불러오기").click().run()
        request.return_value = {**RUN, "status": "EXPIRED"}
        next(b for b in app.button if b.label == "선택한 실행 조회").click().run()
        assert not app.exception
        assert request.call_args.args == ("GET", "/v1/ticket-runs/run-1")
        assert any("만료됨" in item.value for item in app.markdown)
        assert not any(b.label in {"승인하고 티켓 생성", "거절", "저장된 실행 재개"} for b in app.button)
        assert not app.success


def test_stale_approval_failure_is_not_success_then_refresh_expires(monkeypatch):
    monkeypatch.setenv("M3_ENABLED", "true")
    monkeypatch.setenv("M2_ENABLED", "false")
    with patch("tickets_ui.ticket_request", return_value=RUN) as request:
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        next(b for b in app.button if b.label == "초안 등록 · 승인 대기").click().run()
        request.side_effect = RuntimeError("승인 만료: 상태를 조회하세요.")
        next(b for b in app.button if b.label == "승인하고 티켓 생성").click().run()
        assert not app.exception
        assert app.error and not app.success
        request.side_effect = None
        request.return_value = {**RUN, "status": "EXPIRED"}
        next(b for b in app.button if b.label == "실행 상태 새로고침").click().run()
        assert any("만료됨" in item.value for item in app.markdown)
        assert not any(b.label == "승인하고 티켓 생성" for b in app.button)
