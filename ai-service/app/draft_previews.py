import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.approvals import StrictModel
from app.models import IncidentQuery
from app.agent.answers import AnswerFailure, redact
from app.agent.guardrails import guard
from app.agent.draft_preview import PROMPT_VERSION, generate_preview
from app.rag.store import RagUnavailable


class PreviewRequest(StrictModel):
    query: str = Field(min_length=1, max_length=4000)
    incident_id: str = Field(min_length=1, max_length=32)
    incident_filters: IncidentQuery


def draft_preview_router(identity, reader, error_type):
    router = APIRouter()

    def operator(principal=Depends(identity)):
        if principal[1] != "operator":
            raise error_type(403, "FORBIDDEN", "운영자 권한이 필요합니다.")
        return principal

    @router.post("/v1/ticket-draft-previews")
    async def preview(request: Request, payload: PreviewRequest, principal=Depends(operator)):
        if guard(payload.query) == "DENIED":
            raise error_type(422, "UNSAFE_REQUEST", "허용되지 않은 요청입니다.")
        runtime = request.app.state.answers
        if runtime is None or runtime.generator.mode != "compatible" or runtime.generator.client is None:
            raise error_type(503, "LLM_NOT_ENABLED", "초안 생성용 LLM 연결이 필요합니다.")
        try:
            async with asyncio.timeout(45):
                page = await reader(request, payload.incident_filters, principal)
                rows = [r for r in page.items if r.id == payload.incident_id]
                if not rows:
                    raise error_type(404, "INCIDENT_NOT_IN_RESULTS", "조회 범위에서 선택한 장애를 찾지 못했습니다.")
                incident = rows[0].model_dump(mode="json")
                if incident["status"] == "RESOLVED":
                    raise error_type(409, "INCIDENT_RESOLVED", "이미 해결된 장애입니다.")
                citations = await asyncio.to_thread(runtime.store.search,
                    redact(f'{payload.query}\n{incident["category"]} {incident["severity"]} {incident["cause"]}'), principal[1])
                draft, used = await generate_preview(runtime.generator.client, payload.query, incident, citations)
                return {"draft": draft.model_dump(mode="json") if draft else None, "citations": used,
                        "abstain": draft is None, "mode": "llm_preview", "prompt_version": PROMPT_VERSION,
                        "observed_at": datetime.now(timezone.utc).isoformat(), "request_id": request.state.request_id,
                        "message": "근거가 부족해 초안을 보류했습니다." if draft is None else "미등록 초안입니다. 내용과 근거를 검토하세요."}
        except RagUnavailable:
            raise error_type(503, "RAG_UNAVAILABLE", "검색 근거를 가져오지 못했습니다.", True) from None
        except AnswerFailure:
            raise error_type(502, "DRAFT_GENERATION_FAILED", "초안 생성·출처 검증에 실패했습니다.") from None
        except TimeoutError:
            raise error_type(504, "DRAFT_TIMEOUT", "초안 생성 시간이 초과됐습니다.", True) from None

    return router
