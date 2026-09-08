"""승인 대기와 쓰기를 분리한 그래프. 저장소와 인증된 Spring client는 실행 계층이 주입합니다."""
from typing import Protocol, TypedDict


class TicketState(TypedDict, total=False):
    run_id: str
    owner_id: str
    draft: dict
    approval_id: str
    draft_hash: str
    approval: dict
    ticket_id: str
    status: str


class Ledger(Protocol):
    async def propose(self, run_id: str, owner_id: str, draft: dict) -> dict: ...
    async def get(self, approval_id: str, owner_id: str) -> dict: ...
    async def create_ticket(self, approval_id: str, draft_hash: str, owner_id: str, key: str) -> dict: ...


class LedgerMismatch(RuntimeError):
    pass


def verify(approval: dict, state: TicketState):
    if (approval.get("owner_id") != state["owner_id"]
            or approval.get("run_id") != state["run_id"]
            or approval.get("approval_id") != state["approval_id"]
            or approval.get("draft_hash") != state["draft_hash"]):
        raise LedgerMismatch("승인 원장과 실행 상태가 일치하지 않습니다.")
    if approval.get("status") not in {"PENDING", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED"}:
        raise LedgerMismatch("알 수 없는 승인 상태입니다.")


def build_ticket_graph(ledger: Ledger, checkpointer):
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    if checkpointer is None:
        raise ValueError("승인 그래프에는 체크포인트 저장소가 필요합니다.")

    async def propose(state):
        approval = await ledger.propose(state["run_id"], state["owner_id"], state["draft"])
        updated = {**state, "approval_id": approval["approval_id"], "draft_hash": approval["draft_hash"]}
        verify(approval, updated)
        return {"approval": approval, "approval_id": approval["approval_id"],
                "draft_hash": approval["draft_hash"], "status": "WAITING_APPROVAL"}

    async def wait(state):
        # 재개 값은 권한이나 승인으로 쓰지 않습니다. 결정은 별도 인증 API가 원장에 저장합니다.
        interrupt({"approval_id": state["approval_id"], "draft": state["approval"]["draft"],
                   "expires_at": state["approval"]["expires_at"]})
        return {}

    async def read(state):
        approval = await ledger.get(state["approval_id"], state["owner_id"])
        verify(approval, state)
        return {"approval": approval}

    def route(state):
        return {"PENDING": "wait", "APPROVED": "execute", "EXECUTED": "finish",
                "REJECTED": "finish", "EXPIRED": "finish"}[state["approval"]["status"]]

    async def execute(state):
        # 대기 노드와 다른 단계이며 재실행에도 같은 키를 사용합니다.
        approval = await ledger.get(state["approval_id"], state["owner_id"])
        verify(approval, state)
        if approval["status"] not in {"APPROVED", "EXECUTED"}:
            return {"approval": approval}
        ticket = await ledger.create_ticket(state["approval_id"], state["draft_hash"], state["owner_id"],
                                            "ticket:" + state["approval_id"])
        if ticket.get("approval_id") != state["approval_id"] or not ticket.get("id"):
            raise LedgerMismatch("티켓과 승인 원장이 일치하지 않습니다.")
        return {"ticket_id": ticket["id"], "approval": {**approval, "status": "EXECUTED", "ticket_id": ticket["id"]}}

    async def finish(state):
        status = state["approval"]["status"]
        if status == "EXECUTED":
            ticket_id = state["approval"].get("ticket_id")
            if not ticket_id:
                raise LedgerMismatch("완료 원장에 티켓이 없습니다.")
            return {"status": "COMPLETED", "ticket_id": ticket_id}
        return {"status": status}

    graph = StateGraph(TicketState)
    for name, node in {"propose": propose, "wait": wait, "read": read, "execute": execute, "finish": finish}.items():
        graph.add_node(name, node)
    graph.add_edge(START, "propose")
    graph.add_edge("propose", "wait")
    graph.add_edge("wait", "read")
    graph.add_conditional_edges("read", route, {"wait": "wait", "execute": "execute", "finish": "finish"})
    graph.add_conditional_edges("execute", lambda s: "wait" if s["approval"]["status"] == "PENDING" else "finish",
                                {"wait": "wait", "finish": "finish"})
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer)
