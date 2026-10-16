#Spring Boot 승인 원장 연동 -> AI가 초안을 만들더라도 임의로 티켓을 생성하는 것이 아니라, 승인과 티켓 생성 요청을 Spring Boot에 전달
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

#다른 데이터 모델들이 공통으로 사용할 검증 규칙
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

#티켓 초안의 데이터 구조
class Draft(StrictModel):
    incident_id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=6000)
    team: str = Field(min_length=1, max_length=80)
    priority: Literal["P1", "P2", "P3"]

#승인 요청 등록 시 전달하는 초안과 실행 식별 정보
class Proposal(StrictModel):
    # 재전송에도 같은 ID를 쓰는 중간 API입니다. 최종 run API에서는 서버가 발급합니다.
    run_id: UUID
    proposal_version: int = Field(default=1, ge=1, strict=True)
    draft: Draft

#승인 또는 거절이라는 사용자 판단
class Decision(StrictModel):
    decision: Literal["approve", "reject"]

#승인 ID와 초안 해시를 포함한 티켓 생성 요청
class TicketRequest(StrictModel):
    approval_id: UUID #어떤 승인을 근거로 티켓을 만드려는지
    draft_hash: str = Field(pattern=r"^[a-f0-9]{64}$") #해당 티켓의 초안 내용과 연결된 해시값

#Spring Boot가 반환하는 승인 기록
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

#Spring Boot가 반환하는 생성된 티켓 정보
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

#권한 확인
#view -> 조회 가능한 API를 이용 가능 / operator -> 승인 등록, 결정, 티켓 생성 같은 쓰기 작업에 필요
def approval_router(identity, error_type):
    router = APIRouter(prefix="/v1", tags=["승인·티켓"])

    def operator(principal=Depends(identity)):
        if principal[1] != "operator":
            raise error_type(403, "FORBIDDEN", "운영자 권한이 필요합니다.")
        return principal

    #Spring Boot로 API 요청 전달
    #여기서 인증 토큰이 두 종류라는 점이 중요합니다.
    # 사용자 → FastAPI 구간에서는 사용자 토큰을 사용하고, FastAPI → Spring Boot 구간에서는 서비스 토큰을 사용합니다.
    # 또한 원래 요청자의 ID와 역할을 별도의 헤더로 전달합니다.
    # Spring Boot는 서비스 호출을 인증한 뒤 전달받은 사용자 정보를 활용해 소유권과 업무 권한을 검사하도록 설계할 수 있습니다. 
    async def forward(request, principal, method, path, model, payload=None, key=None):
        headers = {
            "Authorization": "Bearer " + request.app.state.settings.business_service_token,
            "X-User-ID": principal[0], "X-User-Role": principal[1],
            "X-Request-ID": request.state.request_id,
        }

        #멱등키 전달(멱등키를 생성하거나 DB 중복을 직접 차단하는 부분은 아님)
        if key is not None:
            headers["Idempotency-Key"] = key
            
        try:
            # 응답 유실 처리
            response = await request.app.state.client.request(
                method, path, headers=headers,
                json=payload.model_dump(mode="json") if payload else None,
            )

        #단순히 바로 재요청 하지 않는 이유
        #예를 들어 티켓 생성 요청을 보낸 뒤 Spring Boot가 데이터베이스에 티켓을 저장했지만 FastAPI가 응답을 받지 못했다고 가정
        #이 경우 FastAPI 입장에서는 티켓 생성 성공 여부를 알 수 없음 -> 따라서 쓰기 요청을 무작정 반복하면 안 됩니다. 먼저 원장의 실제 상태를 확인하고, 필요한 경우 동일한 멱등키로 재시도해야 함
        #이 코드에서는 자동 재전송하지 않고 확인이 필요한 오류 반
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
