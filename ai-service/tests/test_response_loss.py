import asyncio
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.agent.ticket_runtime import RunError, SpringLedger

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


worker = load("response_loss_worker")


def test_committed_response_is_lost_once_and_retry_keeps_key():
    async def run():
        ticket = {"id": str(uuid4()), "approval_id": str(uuid4())}
        drops = []
        transport = worker.DropCommittedResponse(httpx.MockTransport(lambda req: httpx.Response(201, json=ticket)),
                                                lambda body, key: drops.append((body, key)))
        async with httpx.AsyncClient(base_url="http://business", transport=transport) as client:
            ledger = SpringLedger(client, "test-token", "demo-operator", "trace")
            with pytest.raises(RunError) as exc:
                await ledger.create_ticket(ticket["approval_id"], "a" * 64, "demo-operator", "same-key")
            assert exc.value.code == "RECONCILING"
            response = await client.post("/api/v1/tickets", headers={"Idempotency-Key": "same-key"})
            assert response.json() == ticket
        assert transport.ticket_keys == ["same-key", "same-key"]
        assert drops == [(ticket, "same-key")]
    asyncio.run(run())


@pytest.mark.parametrize("method,status", [("GET", 200), ("POST", 503)])
def test_noncommitted_or_read_response_is_not_dropped(method, status):
    async def run():
        def forbidden(*args):
            raise AssertionError("Must not inject")
        transport = worker.DropCommittedResponse(httpx.MockTransport(lambda req: httpx.Response(status, json={})), forbidden)
        async with httpx.AsyncClient(base_url="http://business", transport=transport) as client:
            assert (await client.request(method, "/api/v1/tickets")).status_code == status
        assert not transport.dropped
    asyncio.run(run())


def test_orchestrator_cannot_reinject_when_resuming(tmp_path, monkeypatch):
    from types import SimpleNamespace
    runner = load("verify_response_loss")
    folder = tmp_path / "eval/results"
    folder.mkdir(parents=True)
    path = folder / "prior.json"
    report = {"inject_complete": True, "resume_complete": False, "passed": False,
              "approval_id": str(uuid4()), "committed_ticket_id": str(uuid4())}
    path.write_text(json.dumps(report), encoding="utf-8")
    commands = []
    def execute(command, **kwargs):
        commands.append(command)
        if "ps" in command:
            return SimpleNamespace(returncode=0, stdout="a\nb\n")
        if "run" in command:
            assert command[-2] == "resume"
            report["resume_complete"] = True
            path.write_text(json.dumps(report), encoding="utf-8")
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=0, stdout='{"tickets":1,"ticket_audits":1}')
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner.subprocess, "run", execute)
    monkeypatch.setattr("sys.argv", ["verify", "--execute", "--resume-report", str(path)])
    assert runner.main() == 0
    assert not any("inject" in command for command in commands)
    assert json.loads(path.read_text())["passed"]
