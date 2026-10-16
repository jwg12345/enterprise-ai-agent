#AI Agent의 실행을 시작하고 상태를 관리하는 API 계층 
#실제 로직은 TicketRuntime에 위임 -> ai-service/app/agent/ticket_runtime.py의 TicketRuntime 클래스 
import asyncio
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.approvals import Draft, StrictModel

#실행을 시작할 때 구조화된 티켓 초안을 전달받음
class RunDraft(StrictModel):
    draft: Draft #티켓 초안

#사용자가 승인하거나 거절할 때 필요한 데이터 구조
class RunDecision(StrictModel):
    approval_id: UUID
    decision: Literal["approve", "reject"]


def ticket_runs_router(identity, error_type):
    router = APIRouter(prefix="/v1/ticket-runs", tags=["영속 티켓 실행"])

    def operator(principal=Depends(identity)):
        if principal[1] != "operator":
            raise error_type(403, "FORBIDDEN", "운영자 권한이 필요합니다.")
        return principal

    #실제 실행 계층 호출 -> 서버 실행 시 생성된 TicketRuntime 객체를 가져옴
    async def invoke(request, principal, **kwargs):
        runtime = request.app.state.tickets #
        if runtime is None:
            raise error_type(503, "M3_NOT_ENABLED", "승인 실행 기능이 준비되지 않았습니다.")
        from app.agent.ticket_runtime import RunError
        try:
            async with asyncio.timeout(45): #실행 계층 호출에 45초 제한 설정
                if kwargs.pop("list_only", False):
                    return await runtime.list_runs(principal[0])
                return await runtime.operate(principal[0], request.state.request_id, **kwargs) # 실제 작업을 TicketRuntime.operate()에 위임
        except RunError as exc:
            raise error_type(exc.status, exc.code, "실행 상태를 조회하고 승인 내용을 확인하세요.", exc.status >= 500) from None
        except TimeoutError:
            raise error_type(504, "RECONCILING", "처리 결과 확인이 필요합니다. 같은 실행을 조회하세요.", True) from None
        except Exception:
            raise error_type(503, "RUN_UNAVAILABLE", "실행 저장소 또는 업무 연결을 확인하세요.", True) from None

    #run id : 하나의 실행을 식별하는 값 / approval_id : 승인 기록을 식별하는 값
    
    #새로운 티켓 실행 시작
    #action="start"로 실행 시작을 요청 / 여기서 HTTP 헤더로 받은 멱등키를 함께 전달(Idempotency-Key)
    @router.post("")
    async def create(request: Request, payload: RunDraft,
                     idempotency_key: str = Header(pattern=r"^[A-Za-z0-9._:-]{1,128}$"), principal=Depends(operator)):
        return await invoke(request, principal, draft=payload.draft.model_dump(mode="json"), key=idempotency_key, action="start")

    #실행 목록 조회
    @router.get("")
    async def listing(request: Request, principal=Depends(operator)):
        return await invoke(request, principal, list_only=True)

    #특정 실행 상태 조회
    @router.get("/{run_id}")
    async def get(request: Request, run_id: UUID, principal=Depends(operator)):
        return await invoke(request, principal, run_id=str(run_id))

    #사용자 승인 또는 거절
    @router.post("/{run_id}/decisions")
    async def decide(request: Request, run_id: UUID, payload: RunDecision, principal=Depends(operator)):
        return await invoke(request, principal, run_id=str(run_id), action="decision",
                            approval_id=str(payload.approval_id), decision=payload.decision)

    #기존 실행 재개
    @router.post("/{run_id}/resume")
    async def resume(request: Request, run_id: UUID, principal=Depends(operator)):
        return await invoke(request, principal, run_id=str(run_id), action="resume")

    return router
