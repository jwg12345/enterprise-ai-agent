"""Spring 승인 원장에 대한 인증된 HTTP 경계. 자동 승인/티켓 실행은 하지 않습니다."""
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Draft(StrictModel):
    incident_id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=6000)
    team: str = Field(min_length=1, max_length=80)
    priority: Literal["P1", "P2", "P3"]


class Proposal(StrictModel):
    # 재전송에도 같은 ID를 쓰는 중간 API입니다. 최종 run API에서는 서버가 발급합니다.
    run_id: UUID
    proposal_version: int = Field(default=1, ge=1, strict=True)
    draft: Draft


class Decision(StrictModel):
    decision: Literal["approve", "reject"]


class TicketRequest(StrictModel):
    approval_id: UUID
    draft_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Approval(StrictModel):
    approval_id: UUID
    run_id: UUID
    proposal_version: int
    owner_id: str
    draft: Draft
    draft_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED"]
    expires_at: AwareDatetime
    ticket_id: UUID | None


class Ticket(StrictModel):
    id: UUID
    approval_id: UUID
    incident_id: str
    title: str
    body: str
    team: str
    priority: Literal["P1", "P2", "P3"]
    status: Literal["OPEN", "CLOSED"]
    created_at: AwareDatetime


CONFLICTS = {
    "APPROVAL_EXPIRED", "APPROVAL_REQUIRED", "DECISION_CONFLICT", "DRAFT_MISMATCH",
    "IDEMPOTENCY_CONFLICT", "INCIDENT_RESOLVED", "PROPOSAL_IMMUTABLE", "PROPOSAL_CONFLICT",
}


def approval_router(identity, error_type):
    router = APIRouter(prefix="/v1", tags=["승인·티켓"])

    def operator(principal=Depends(identity)):
        if principal[1] != "operator":
            raise error_type(403, "FORBIDDEN", "운영자 권한이 필요합니다.")
        return principal

    async def forward(request, principal, method, path, model, payload=None, key=None):
        headers = {
            "Authorization": "Bearer " + request.app.state.settings.business_service_token,
            "X-User-ID": principal[0], "X-User-Role": principal[1],
            "X-Request-ID": request.state.request_id,
        }
        if key is not None:
            headers["Idempotency-Key"] = key
        try:
            # 쓰기 응답 유실 시 자동 재전송하지 않습니다. 호출자가 원장 확인 후 같은 키로 재시도합니다.
            response = await request.app.state.client.request(
                method, path, headers=headers,
                json=payload.model_dump(mode="json") if payload else None,
            )
        except httpx.TimeoutException:
            raise error_type(504, "BUSINESS_TIMEOUT", "처리 결과를 확인하지 못했습니다. 원장을 조회하세요.", True) from None
        except httpx.HTTPError:
            raise error_type(502, "BUSINESS_UNAVAILABLE", "업무 서비스에 연결할 수 없습니다.", True) from None
        if response.status_code in {403, 404, 409, 422}:
            code = {403: "FORBIDDEN", 404: "NOT_FOUND", 409: "STATE_CONFLICT", 422: "INVALID_REQUEST"}[response.status_code]
            if response.status_code == 409:
                try:
                    candidate = response.json()["error"]["code"]
                    if isinstance(candidate, str) and candidate in CONFLICTS:
                        code = candidate
                except (ValueError, KeyError, TypeError):
                    pass
            raise error_type(response.status_code, code, "요청 권한·승인 상태·입력 내용을 확인하세요.")
        allowed = {200, 201} if method == "POST" else {200}
        if response.status_code not in allowed:
            raise error_type(502, "BUSINESS_UNAVAILABLE", "업무 처리 결과를 확인할 수 없습니다.", True)
        try:
            result = model.model_validate(response.json())
            if isinstance(result, Approval) and result.owner_id != principal[0]:
                raise ValueError("Owner mismatch")
        except (ValidationError, ValueError):
            raise error_type(502, "INVALID_BUSINESS_RESPONSE", "업무 응답 형식이 올바르지 않습니다.") from None
        return JSONResponse(status_code=response.status_code, content=result.model_dump(mode="json"))

    @router.post("/approvals")
    async def propose(request: Request, payload: Proposal, principal=Depends(operator)):
        return await forward(request, principal, "POST", "/api/v1/approvals", Approval, payload)

    @router.get("/approvals/{approval_id}")
    async def get_approval(request: Request, approval_id: UUID, principal=Depends(identity)):
        return await forward(request, principal, "GET", f"/api/v1/approvals/{approval_id}", Approval)

    @router.post("/approvals/{approval_id}/decision")
    async def decide(request: Request, approval_id: UUID, payload: Decision, principal=Depends(operator)):
        return await forward(request, principal, "POST", f"/api/v1/approvals/{approval_id}/decision", Approval, payload)

    @router.post("/tickets")
    async def create_ticket(request: Request, payload: TicketRequest,
                            idempotency_key: str = Header(pattern=r"^[A-Za-z0-9._:-]{1,128}$"),
                            principal=Depends(operator)):
        return await forward(request, principal, "POST", "/api/v1/tickets", Ticket, payload, idempotency_key)

    @router.get("/tickets/{ticket_id}")
    async def get_ticket(request: Request, ticket_id: UUID, principal=Depends(identity)):
        return await forward(request, principal, "GET", f"/api/v1/tickets/{ticket_id}", Ticket)

    return router
