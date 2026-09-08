"""실제 LangGraph + 테스트 전용 메모리 저장소. DB 영속성 검사는 아닙니다."""
import asyncio
from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent.ticket_graph import LedgerMismatch, build_ticket_graph


class FakeLedger:
    def __init__(self):
        self.approval = None
        self.keys = []
        self.tickets = {}
        self.lose_response = False
        self.proposals = 0

    async def propose(self, run_id, owner_id, draft):
        self.proposals += 1
        if self.approval is None:
            self.approval = {"run_id": run_id, "owner_id": owner_id, "draft": draft,
                             "approval_id": "approval-1", "draft_hash": "a" * 64,
                             "status": "PENDING", "expires_at": "2026-09-07T00:00:00Z", "ticket_id": None}
        return deepcopy(self.approval)

    async def get(self, approval_id, owner_id):
        return deepcopy(self.approval)

    async def create_ticket(self, approval_id, draft_hash, owner_id, key):
        assert self.approval["status"] in {"APPROVED", "EXECUTED"}
        self.keys.append(key)
        self.tickets.setdefault(key, {"id": "ticket-1", "approval_id": approval_id})
        self.approval.update(status="EXECUTED", ticket_id="ticket-1")
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError("simulated response loss")
        return self.tickets[key]


INITIAL = {"run_id": "run-1", "owner_id": "operator-1", "draft": {"title": "합성 점검"}}
CONFIG = {"configurable": {"thread_id": "run-1"}, "recursion_limit": 12}


def test_interrupt_never_creates_ticket_and_untrusted_resume_cannot_approve():
    async def run():
        ledger = FakeLedger()
        graph = build_ticket_graph(ledger, InMemorySaver())
        first = await graph.ainvoke(INITIAL, CONFIG)
        assert first["__interrupt__"] and not ledger.keys
        second = await graph.ainvoke(Command(resume={"approved": True}), CONFIG)
        assert second["__interrupt__"] and not ledger.keys
        assert ledger.proposals == 1
    asyncio.run(run())


@pytest.mark.parametrize("decision,expected", [("APPROVED", "COMPLETED"), ("REJECTED", "REJECTED"), ("EXPIRED", "EXPIRED")])
def test_ledger_controls_resume_after_graph_reconstruction(decision, expected):
    async def run():
        ledger, saver = FakeLedger(), InMemorySaver()
        await build_ticket_graph(ledger, saver).ainvoke(INITIAL, CONFIG)
        ledger.approval["status"] = decision
        graph = build_ticket_graph(ledger, saver)
        result = await graph.ainvoke(Command(resume="wake"), CONFIG)
        assert result["status"] == expected
        assert len(ledger.tickets) == (1 if decision == "APPROVED" else 0)
        assert ledger.proposals == 1
    asyncio.run(run())


@pytest.mark.parametrize("field,value", [("owner_id", "other"), ("draft_hash", "b" * 64), ("run_id", "other")])
def test_ledger_mismatch_stops_write(field, value):
    async def run():
        ledger = FakeLedger()
        graph = build_ticket_graph(ledger, InMemorySaver())
        await graph.ainvoke(INITIAL, CONFIG)
        ledger.approval.update(status="APPROVED", **{field: value})
        with pytest.raises(LedgerMismatch):
            await graph.ainvoke(Command(resume=True), CONFIG)
        assert not ledger.keys
    asyncio.run(run())


def test_response_loss_retry_uses_same_key_and_does_not_duplicate():
    async def run():
        ledger, saver = FakeLedger(), InMemorySaver()
        graph = build_ticket_graph(ledger, saver)
        await graph.ainvoke(INITIAL, CONFIG)
        ledger.approval["status"] = "APPROVED"
        ledger.lose_response = True
        with pytest.raises(TimeoutError):
            await graph.ainvoke(Command(resume="wake"), CONFIG)
        result = await build_ticket_graph(ledger, saver).ainvoke(None, CONFIG)
        assert result["status"] == "COMPLETED"
        assert len(ledger.tickets) == 1
        assert ledger.keys == ["ticket:approval-1", "ticket:approval-1"]
    asyncio.run(run())
