"""인증된 실행 계층: 업무 쓰기는 Spring, 실행 소유권과 체크포인트는 agent DB."""
import hashlib
import asyncio
import json
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.approvals import Approval, Ticket, CONFLICTS
from app.agent.checkpoints import open_checkpointer
from app.agent.ticket_graph import build_ticket_graph, LedgerMismatch


class RunError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class SpringLedger:
    def __init__(self, client, token, owner, trace):
        self.client = client
        self.headers = {"Authorization": "Bearer " + token, "X-User-ID": owner,
                        "X-User-Role": "operator", "X-Request-ID": trace}
        self.owner = owner

    async def request(self, method, path, model, payload=None, key=None):
        headers = dict(self.headers)
        if key:
            headers["Idempotency-Key"] = key
        try:
            response = await self.client.request(method, path, headers=headers, json=payload)
        except httpx.HTTPError:
            raise RunError(503, "RECONCILING") from None
        if response.status_code not in {200, 201}:
            code = "BUSINESS_UNAVAILABLE"
            try:
                candidate = response.json()["error"]["code"]
                if isinstance(candidate, str) and candidate in CONFLICTS:
                    code = candidate
            except (ValueError, KeyError, TypeError):
                pass
            raise RunError(response.status_code if response.status_code in {403, 404, 409, 422} else 503, code)
        try:
            result = model.model_validate(response.json()).model_dump(mode="json")
            if model is Approval and result["owner_id"] != self.owner:
                raise ValueError("owner")
            return result
        except (ValueError, ValidationError):
            raise RunError(502, "INVALID_BUSINESS_RESPONSE") from None

    async def propose(self, run_id, owner_id, draft):
        return await self.request("POST", "/api/v1/approvals", Approval,
                                  {"run_id": run_id, "proposal_version": 1, "draft": draft})

    async def get(self, approval_id, owner_id):
        return await self.request("GET", "/api/v1/approvals/" + approval_id, Approval)

    async def decide(self, approval_id, decision):
        return await self.request("POST", "/api/v1/approvals/" + approval_id + "/decision", Approval,
                                  {"decision": decision})

    async def create_ticket(self, approval_id, draft_hash, owner_id, key):
        return await self.request("POST", "/api/v1/tickets", Ticket,
                                  {"approval_id": approval_id, "draft_hash": draft_hash}, key)


class TicketRuntime:
    def __init__(self, client, token):
        self.client, self.token = client, token

    async def setup(self):
        async with open_checkpointer() as saver:
            await saver.conn.execute("SELECT pg_advisory_lock(7303002)")
            try:
                await saver.conn.execute("""CREATE TABLE IF NOT EXISTS agent.ticket_runs (
                    run_id uuid PRIMARY KEY, owner_id text NOT NULL, request_key varchar(128) NOT NULL,
                    draft_hash char(64) NOT NULL, draft_json jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(owner_id, request_key))""")
            finally:
                await saver.conn.execute("SELECT pg_advisory_unlock(7303002)")

    async def ready(self):
        try:
            async with asyncio.timeout(3):
                async with open_checkpointer(initialize=False) as saver:
                    await saver.conn.execute("SELECT run_id FROM agent.ticket_runs LIMIT 0")
                    return True
        except Exception:
            return False

    async def list_runs(self, owner):
        async with open_checkpointer(initialize=False) as saver:
            cursor = await saver.conn.execute(
                "SELECT run_id,created_at FROM agent.ticket_runs WHERE owner_id=%s ORDER BY created_at DESC LIMIT 20",
                (owner,))
            return {"items": [{"run_id": str(r["run_id"]), "created_at": r["created_at"].isoformat()}
                              for r in await cursor.fetchall()]}

    async def operate(self, owner, trace, run_id=None, draft=None, key=None, action="get", decision=None, approval_id=None):
        from langgraph.types import Command

        async with open_checkpointer(initialize=False) as saver:
            conn = saver.conn
            if draft is not None:
                encoded = json.dumps(draft, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                digest = hashlib.sha256(encoded.encode()).hexdigest()
                await conn.execute("""INSERT INTO agent.ticket_runs(run_id,owner_id,request_key,draft_hash,draft_json)
                    VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT(owner_id,request_key) DO NOTHING""",
                    (uuid4(), owner, key, digest, encoded))
                cursor = await conn.execute("SELECT * FROM agent.ticket_runs WHERE owner_id=%s AND request_key=%s", (owner, key))
                row = await cursor.fetchone()
                if row["draft_hash"] != digest:
                    raise RunError(409, "IDEMPOTENCY_CONFLICT")
                run_id = str(row["run_id"])
            else:
                cursor = await conn.execute("SELECT * FROM agent.ticket_runs WHERE run_id=%s AND owner_id=%s", (run_id, owner))
                row = await cursor.fetchone()
                if row is None:
                    raise RunError(404, "NOT_FOUND")
            lock = await conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", ("run:" + run_id,))
            if not (await lock.fetchone())["acquired"]:
                raise RunError(409, "RUN_BUSY")
            try:
                ledger = SpringLedger(self.client, self.token, owner, trace)
                graph = build_ticket_graph(ledger, saver)
                config = {"configurable": {"thread_id": "ticket-run:" + run_id}, "recursion_limit": 12}
                snapshot = await graph.aget_state(config)
                if action != "get":
                    if not snapshot.values:
                        if action == "decision":
                            raise RunError(409, "APPROVAL_NOT_READY")
                        await graph.ainvoke({"run_id": run_id, "owner_id": owner, "draft": row["draft_json"]}, config)
                    else:
                        state = snapshot.values
                        if action == "decision":
                            if approval_id != state.get("approval_id"):
                                raise RunError(409, "APPROVAL_MISMATCH")
                            await ledger.decide(approval_id, decision)
                        if snapshot.next:
                            interrupted = any(task.interrupts for task in snapshot.tasks)
                            await graph.ainvoke(Command(resume="wake") if interrupted else None, config)
                    snapshot = await graph.aget_state(config)
                state = snapshot.values
                approval = await ledger.get(state["approval_id"], owner) if state.get("approval_id") else None
                status = {"PENDING": "WAITING_APPROVAL", "APPROVED": "RECONCILING", "EXECUTED": "COMPLETED",
                          "REJECTED": "REJECTED", "EXPIRED": "EXPIRED"}.get(approval["status"] if approval else "", "RUNNING")
                return {"run_id": run_id, "status": status, "approval": approval,
                        "ticket_id": approval.get("ticket_id") if approval else None}
            except LedgerMismatch:
                raise RunError(409, "LEDGER_MISMATCH") from None
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", ("run:" + run_id,))
