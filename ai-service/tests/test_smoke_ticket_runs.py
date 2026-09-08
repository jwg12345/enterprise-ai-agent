"""재시작 검사 재개 시 새 업무 요청 없이 저장된 실행만 사용하는지 검증합니다."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/smoke_ticket_runs.py"
spec = importlib.util.spec_from_file_location("smoke_ticket_runs", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_resume_restarts_with_rag_and_never_registers_new_run(tmp_path, monkeypatch):
    rows = [{"decision": d, "run_id": str(uuid4()), "approval_id": str(uuid4()), "key": str(uuid4())}
            for d in ("reject", "approve")]
    source = tmp_path / "failed.json"
    original = json.dumps({"passed": False, "failed_step": "restart AI", "runs": rows})
    source.write_text(original, encoding="utf-8")
    (tmp_path / ".env").write_text("DEMO_OPERATOR_TOKEN=test-operator\nDEMO_VIEWER_TOKEN=test-viewer\n", encoding="utf-8")
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["smoke", "--restart", "--resume-report", str(source)])
    commands = []
    def execute(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(smoke.subprocess, "run", execute)
    paths = []
    def open_request(request, **kwargs):
        path = request.full_url.removeprefix("http://127.0.0.1:8000")
        paths.append(path)
        if path == "/health/ready":
            body = {"stage": "M3"}
        elif path.endswith("/decisions"):
            decision = json.loads(request.data)["decision"]
            body = {"status": "REJECTED" if decision == "reject" else "COMPLETED",
                    "ticket_id": None if decision == "reject" else "ticket-1"}
        else:
            assert request.method == "GET"
            assert path in ["/v1/ticket-runs/" + r["run_id"] for r in rows]
            body = {"status": "WAITING_APPROVAL"}
        response = io.BytesIO(json.dumps(body).encode())
        response.status = 200
        return response
    monkeypatch.setattr(smoke, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    assert smoke.main() == 0
    assert commands[0][-4:] == ["--profile", "rag", "restart", "ai"]
    assert "/v1/ticket-runs" not in paths
    assert source.read_text(encoding="utf-8") == original
    result = json.loads(next((tmp_path / "eval/results").glob("*.json")).read_text(encoding="utf-8"))
    assert result["passed"] and result["resumed_from"] == "failed.json"
    assert [r["run_id"] for r in result["runs"]] == [r["run_id"] for r in rows]


def test_successful_report_cannot_be_replayed(tmp_path):
    path = tmp_path / "passed.json"
    path.write_text(json.dumps({"passed": True, "runs": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        smoke.resume_runs(path)


def test_readiness_retries_connection_reset_and_incomplete_response(monkeypatch):
    from http.client import RemoteDisconnected
    failures = [ConnectionResetError(), RemoteDisconnected(), ValueError(), (200, {"stage": "M3"})]
    monkeypatch.setattr(smoke.time, "sleep", lambda _: None)
    def call(*args):
        item = failures.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    smoke.wait_ready(call)
    assert not failures


def test_readiness_has_bounded_wait(monkeypatch):
    ticks = iter([0, 301])
    monkeypatch.setattr(smoke.time, "monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError):
        smoke.wait_ready(lambda *args: (503, {"status": "DOWN"}))
