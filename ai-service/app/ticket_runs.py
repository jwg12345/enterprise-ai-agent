"""수동 구조화 초안용 실행 API. 자연어 runs API와 구분합니다."""
import asyncio
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.approvals import Draft, StrictModel


class RunDraft(StrictModel):
    draft: Draft


class RunDecision(StrictModel):
    approval_id: UUID
    decision: Literal["approve", "reject"]


def ticket_runs_router(identity, error_type):
    router = APIRouter(prefix="/v1/ticket-runs", tags=["영속 티켓 실행"])

    def operator(principal=Depends(identity)):
        if principal[1] != "operator":
            raise error_type(403, "FORBIDDEN", "운영자 권한이 필요합니다.")
        return principal

    async def invoke(request, principal, **kwargs):
        runtime = request.app.state.tickets
        if runtime is None:
            raise error_type(503, "M3_NOT_ENABLED", "승인 실행 기능이 준비되지 않았습니다.")
        from app.agent.ticket_runtime import RunError
        try:
            async with asyncio.timeout(45):
                if kwargs.pop("list_only", False):
                    return await runtime.list_runs(principal[0])
                return await runtime.operate(principal[0], request.state.request_id, **kwargs)
        except RunError as exc:
            raise error_type(exc.status, exc.code, "실행 상태를 조회하고 승인 내용을 확인하세요.", exc.status >= 500) from None
        except TimeoutError:
            raise error_type(504, "RECONCILING", "처리 결과 확인이 필요합니다. 같은 실행을 조회하세요.", True) from None
        except Exception:
            raise error_type(503, "RUN_UNAVAILABLE", "실행 저장소 또는 업무 연결을 확인하세요.", True) from None

    @router.post("")
    async def create(request: Request, payload: RunDraft,
                     idempotency_key: str = Header(pattern=r"^[A-Za-z0-9._:-]{1,128}$"), principal=Depends(operator)):
        return await invoke(request, principal, draft=payload.draft.model_dump(mode="json"), key=idempotency_key, action="start")

    @router.get("")
    async def listing(request: Request, principal=Depends(operator)):
        return await invoke(request, principal, list_only=True)

    @router.get("/{run_id}")
    async def get(request: Request, run_id: UUID, principal=Depends(operator)):
        return await invoke(request, principal, run_id=str(run_id))

    @router.post("/{run_id}/decisions")
    async def decide(request: Request, run_id: UUID, payload: RunDecision, principal=Depends(operator)):
        return await invoke(request, principal, run_id=str(run_id), action="decision",
                            approval_id=str(payload.approval_id), decision=payload.decision)

    @router.post("/{run_id}/resume")
    async def resume(request: Request, run_id: UUID, principal=Depends(operator)):
        return await invoke(request, principal, run_id=str(run_id), action="resume")

    return router
