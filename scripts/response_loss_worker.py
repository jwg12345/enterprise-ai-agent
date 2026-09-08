"""실제 Spring 응답을 검사 transport에서 유실시킵니다. 운영 서버의 장애 스위치는 없습니다."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx


class DropCommittedResponse(httpx.AsyncBaseTransport):
    def __init__(self, inner, on_drop=None):
        self.inner, self.on_drop = inner, on_drop
        self.ticket_keys = []
        self.dropped = False

    async def handle_async_request(self, request):
        is_ticket = request.method == "POST" and request.url.path == "/api/v1/tickets"
        if is_ticket:
            self.ticket_keys.append(request.headers.get("Idempotency-Key"))
        response = await self.inner.handle_async_request(request)
        if is_ticket and self.on_drop and not self.dropped and response.status_code in {200, 201}:
            await response.aread()
            ticket = response.json()
            UUID(ticket["id"])
            self.on_drop(ticket, request.headers.get("Idempotency-Key"))
            self.dropped = True
            await response.aclose()
            raise httpx.ReadError("Injected response loss after committed ticket", request=request)
        return response

    async def aclose(self):
        await self.inner.aclose()


def save(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


async def run(phase, path, report):
    from app.agent.checkpoints import open_checkpointer
    from app.agent.ticket_graph import build_ticket_graph
    from app.agent.ticket_runtime import RunError, SpringLedger, TicketRuntime

    owner = "demo-operator"
    token = os.environ["BUSINESS_SERVICE_TOKEN"]
    def dropped(ticket, key):
        if ticket["approval_id"] != report["approval_id"] or key != "ticket:" + report["approval_id"]:
            raise RuntimeError("Unexpected ticket identity")
        report.update(fault_injected=True, committed_ticket_id=ticket["id"], lost_key=key)
        save(path, report)
    transport = DropCommittedResponse(httpx.AsyncHTTPTransport(retries=0), dropped if phase == "inject" else None)
    async with httpx.AsyncClient(base_url=os.environ["BUSINESS_API_URL"], transport=transport,
                                trust_env=False, timeout=10) as client:
        runtime = TicketRuntime(client, token)
        await runtime.setup()
        if phase == "inject":
            if report.get("fault_injected") or report.get("run_id"):
                raise RuntimeError("Existing execution: resume instead of creating another")
            draft = {"incident_id": "INC-014", "title": "[M4 response loss] 합성 복구 검사",
                     "body": "승인된 합성 티켓의 응답 유실과 중복 방지 검사", "team": "Platform", "priority": "P1"}
            result = await runtime.operate(owner, str(uuid4()), draft=draft, key=report["request_key"], action="start")
            if result["status"] != "WAITING_APPROVAL" or result.get("ticket_id"):
                raise RuntimeError("Expected approval wait")
            report.update(run_id=result["run_id"], approval_id=result["approval"]["approval_id"])
            save(path, report)
            try:
                await runtime.operate(owner, str(uuid4()), run_id=report["run_id"], action="decision",
                                      approval_id=report["approval_id"], decision="approve")
            except RunError as exc:
                if exc.code != "RECONCILING" or not transport.dropped:
                    raise
                report["client_error"] = exc.code
            else:
                raise RuntimeError("Lost response must not report success")
            async with open_checkpointer(initialize=False) as saver:
                graph = build_ticket_graph(SpringLedger(client, token, owner, str(uuid4())), saver)
                snapshot = await graph.aget_state({"configurable": {"thread_id": "ticket-run:" + report["run_id"]}})
                report["pending_nodes_after_loss"] = list(snapshot.next)
                if "execute" not in snapshot.next or snapshot.values.get("ticket_id"):
                    raise RuntimeError("Expected unacknowledged execute checkpoint")
            report["inject_complete"] = True
        else:
            if not report.get("inject_complete"):
                raise RuntimeError("Verified fault injection required")
            for field in ("run_id", "approval_id", "committed_ticket_id"):
                UUID(report[field])
            for _ in range(2):
                result = await runtime.operate(owner, str(uuid4()), run_id=report["run_id"], action="resume")
                if result["status"] != "COMPLETED" or result["ticket_id"] != report["committed_ticket_id"]:
                    raise RuntimeError("Recovery identity mismatch")
            if not transport.ticket_keys or any(k != report["lost_key"] for k in transport.ticket_keys):
                raise RuntimeError("Recovery must reuse original ticket key")
            report.update(resume_complete=True, recovery_ticket_keys=transport.ticket_keys)
        save(path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inject", "resume"))
    parser.add_argument("report")
    args = parser.parse_args()
    if Path(args.report).name != args.report or not args.report.endswith(".json"):
        parser.error("Report filename only")
    path = Path("/results") / args.report
    report = json.loads(path.read_text(encoding="utf-8"))
    try:
        asyncio.run(run(args.phase, path, report))
        print("PASS:", args.phase, flush=True)
        return 0
    except Exception as exc:
        report.update(failed_phase=args.phase, error_type=type(exc).__name__)
        save(path, report)
        print("FAIL:", args.phase, type(exc).__name__, "기존 보고서를 보존합니다.", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
