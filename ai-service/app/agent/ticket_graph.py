"""승인 대기와 쓰기를 분리한 그래프. 저장소와 인증된 Spring client는 실행 계층이 주입합니다."""
#승인 대기 및 티켓 생성 그래프(승인 요청, 사람의 결정 대기, 승인 원장 확인, 티켓 생성 담당)
from typing import Protocol, TypedDict

#승인 실행 상태
class TicketState(TypedDict, total=False):
    run_id: str #한 번의 티켓 처리 흐름을 구분하는 ID (에이전트의 실행 흐름의 ID)
    owner_id: str #해당 작업의 소유자 
    draft: dict #승인받을 점검 요청서 초안
    approval_id: str #Spring 업무 시스템의 승인 요청 ID (승인 요청 식별)
    draft_hash: str #승인 대상 초안의 해시
    approval: dict #Spring의 승인 원장 정보
    ticket_id: str #생성된 티켓 ID (최종 생성된 업무 티켓의 ID)
    status: str #그래프 처리 상태
 
#업무 시스템 인터페이
class Ledger(Protocol):
    async def propose(self, run_id: str, owner_id: str, draft: dict) -> dict: ... #승인 요청 생성
    async def get(self, approval_id: str, owner_id: str) -> dict: ... #승인 상태 조회
    async def create_ticket(self, approval_id: str, draft_hash: str, owner_id: str, key: str) -> dict: ... #최종 티켓 생성


class LedgerMismatch(RuntimeError):
    pass

#승인 원장과 그래프 상태 비교 (승인 원장에 기록된 값과 LangGraph의 실행 상태가 일치해야함 -> 모두 일치해야 다음 단계로 감 / 핵심 검증 로직)
#다른 사람의 승인이나 다른 초안에 대해 승인을 현재 작업에 잘못 적용하지 않도록 하기 위함
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

    #Spring Boot에 승인 요청을 생성하도록 요청(Spring에서 반환한 승인 정보의 ID와 해시를 상태에 저장)
    async def propose(state):
        approval = await ledger.propose(state["run_id"], state["owner_id"], state["draft"])
        updated = {**state, "approval_id": approval["approval_id"], "draft_hash": approval["draft_hash"]}
        verify(approval, updated)
        return {"approval": approval, "approval_id": approval["approval_id"],
                "draft_hash": approval["draft_hash"], "status": "WAITING_APPROVAL"}

    #사람의 승인을 기다리는 단계 
    async def wait(state):   
        #interrupt()를 호출하면 그래프의 실행을 일시 중단하고, 체크포인트를 통해 나중에 이어서 실행할 수 있도록 함
        #중단 시 승인 ID, 검토할 초안, 승인 만료 시간을 전달
        #즉, 그래프가 계속 실행되면서 승인 버튼을 감시하는 역할이 아니라
        #실행을 중단하고 상태를 저장한 뒤, 별도의 API 호출이 발생할 때 다시 실행하는 방식
        interrupt({"approval_id": state["approval_id"], "draft": state["approval"]["draft"],
                   "expires_at": state["approval"]["expires_at"]})
        return {}

    #그래프가 재개되면 Spring Boot에서 실제 승인 상태를 다시 확
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
