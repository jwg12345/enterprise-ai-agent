import asyncio
import hmac
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException

from app.config import Settings
from app.agent.answers import AnswerRequest, AnswerFailure
from app.rag.store import RagUnavailable
from app.models import IncidentPage, IncidentQuery

logger = logging.getLogger("enterprise.ai")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings or Settings.from_env()
        async with httpx.AsyncClient(
            base_url=app.state.settings.business_api_url,
            timeout=httpx.Timeout(5, connect=2), transport=transport, trust_env=False
        ) as client:
            app.state.client = client
            app.state.answers = None
            if os.environ.get("M2_ENABLED", "false").lower() == "true":
                from app.agent.service import AnswerService
                app.state.answers = await AnswerService.start()
            try:
                yield
            finally:
                if app.state.answers:
                    await app.state.answers.close()

    app = FastAPI(title="기업 업무 대응 AI · M1 조회 API", lifespan=lifespan)

    @app.middleware("http")
    async def trace(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = incoming if re.fullmatch(r"[A-Za-z0-9-]{1,64}", incoming) else str(uuid.uuid4())
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(), "level": "INFO",
            "service": "ai", "request_id": request.state.request_id,
            "method": request.method, "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000)
        }))
        return response

    def error_response(request: Request, status: int, code: str, message: str, retryable=False):
        return JSONResponse(status_code=status, content={
            "error": {"code": code, "message": message, "retryable": retryable},
            "request_id": request.state.request_id
        })

    @app.exception_handler(ApiError)
    async def api_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(request, 422, "INVALID_QUERY", "조회 조건을 확인하세요.")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code, "HTTP_ERROR", "요청을 처리할 수 없습니다.")

    def identity(request: Request):
        authorization = request.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        conf = request.app.state.settings
        for expected, user, role in [
            (conf.viewer_token, "demo-viewer", "viewer"),
            (conf.operator_token, "demo-operator", "operator")
        ]:
            if hmac.compare_digest(token.encode(), expected.encode()):
                return user, role
        raise ApiError(401, "UNAUTHENTICATED", "인증이 필요합니다.")

    def query(request: Request, principal=Depends(identity)):
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ApiError(422, "INVALID_QUERY", "중복 조회 조건을 사용할 수 없습니다.")
        try:
            return IncidentQuery.model_validate(dict(request.query_params))
        except ValidationError:
            raise ApiError(422, "INVALID_QUERY", "기간·등급·분류·페이지 조건을 확인하세요.") from None

    @app.get("/health/live")
    async def live():
        return {"status": "UP"}

    @app.get("/health/ready")
    async def ready(request: Request):
        try:
            response = await request.app.state.client.get("/actuator/health/readiness")
            healthy = response.status_code == 200 and response.json().get("status") == "UP"
        except (httpx.HTTPError, ValueError, AttributeError):
            healthy = False
        answers = request.app.state.answers
        rag_ready = await answers.ready() if answers else False
        complete = healthy and (rag_ready if answers else True)
        return JSONResponse(status_code=200 if complete else 503, content={
            "status": "UP" if complete else "DOWN", "stage": "M2" if answers else "M1",
            "business": "UP" if healthy else "DOWN",
            "rag": ("UP" if rag_ready else "DOWN") if answers else "NOT_IMPLEMENTED"
        })

    @app.get("/v1/incidents", response_model=IncidentPage)
    async def incidents(request: Request, filters: Annotated[IncidentQuery, Depends(query)],
                        principal=Depends(identity)):
        user, role = principal
        headers = {
            "Authorization": "Bearer " + request.app.state.settings.business_service_token,
            "X-User-ID": user, "X-User-Role": role,
            "X-Request-ID": request.state.request_id
        }
        for attempt in range(3):
            try:
                response = await request.app.state.client.get(
                    "/api/v1/incidents",
                    params=filters.model_dump(mode="json", by_alias=True, exclude_none=True),
                    headers=headers
                )
                if response.status_code in {502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.1 * (2 ** attempt))
                    continue
                if response.status_code != 200:
                    raise ApiError(502, "BUSINESS_UNAVAILABLE", "업무 조회에 실패했습니다.", True)
                try:
                    return IncidentPage.model_validate(response.json())
                except (ValidationError, ValueError):
                    raise ApiError(502, "INVALID_BUSINESS_RESPONSE", "업무 응답 형식이 올바르지 않습니다.") from None
            except httpx.TimeoutException:
                if attempt == 2:
                    raise ApiError(504, "BUSINESS_TIMEOUT", "업무 조회 시간이 초과되었습니다.", True) from None
            except httpx.HTTPError:
                if attempt == 2:
                    raise ApiError(502, "BUSINESS_UNAVAILABLE", "업무 서비스에 연결할 수 없습니다.", True) from None
            await asyncio.sleep(0.1 * (2 ** attempt))
        raise ApiError(502, "BUSINESS_UNAVAILABLE", "업무 조회에 실패했습니다.", True)

    @app.post("/v1/answers")
    async def answer(request: Request, payload: AnswerRequest, principal=Depends(identity)):
        runtime = request.app.state.answers
        if runtime is None:
            raise ApiError(503, "RAG_NOT_ENABLED", "문서 검색 기능이 아직 준비되지 않았습니다.")
        async def business_reader():
            page = await incidents(request, payload.incident_filters, principal)
            return page.model_dump(mode="json")
        try:
            result = await runtime.run(payload.query, principal[1], request.state.request_id,
                                       business_reader if payload.incident_filters else None)
            logger.info(json.dumps({"service": "ai", "request_id": request.state.request_id,
                                    "node": "answer_graph", "mode": result["mode"], "steps": result["steps"],
                                    "prompt_version": result["prompt_version"]}))
            return result
        except RagUnavailable:
            raise ApiError(503, "RAG_UNAVAILABLE", "문서 검색에 실패했습니다.", True) from None
        except AnswerFailure:
            raise ApiError(502, "ANSWER_FAILED", "답변 생성 또는 출처 검증에 실패했습니다.") from None
        except TimeoutError:
            raise ApiError(504, "ANSWER_TIMEOUT", "문서 검색·답변 시간이 초과되었습니다.", True) from None

    return app


app = create_app()
