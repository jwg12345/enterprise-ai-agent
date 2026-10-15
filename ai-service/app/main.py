#FastAPI 서버의 핵심(전체 API가 연결되는 시작점)
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
from app.approvals import approval_router
from app.ticket_runs import ticket_runs_router
from app.draft_previews import draft_preview_router

logger = logging.getLogger("enterprise.ai")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.propagate = False


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable

#FastAPI 애플리케이션 생성
def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings or Settings.from_env()

        #Spring Boot와 통신할 HTTP 클라이언트 / httpx.AsyncClient는 비동기 HTTP 통신을 수행
        async with httpx.AsyncClient(
            base_url=app.state.settings.business_api_url, #base_url : Spring Boot 서버 주소
            timeout=httpx.Timeout(5, connect=2), transport=transport, trust_env=False 
        ) as client: #timeout=5는 HTTP 요청에 적용되는 기본 타임아웃 설정, connect=2는 연결 수립 단계에 2초 타임아웃을 지정, trust_env=False는 환경변수에 설정된 프록시 등의 HTTP 클라이언트 환경 설정을 사용하지 않도록 합니다.
            app.state.client = client
            app.state.answers = None
            app.state.tickets = None

            #M2, M3 서비스 초기화
            if os.environ.get("M3_ENABLED", "false").lower() == "true": #M3_ENABLED=true -> 티켓 실행 기능 활성화
                from app.agent.ticket_runtime import TicketRuntime
                app.state.tickets = TicketRuntime(client, app.state.settings.business_service_token)
                await app.state.tickets.setup()
            if os.environ.get("M2_ENABLED", "false").lower() == "true": #M2_ENABLED=true -> RAG 답변 기능 활성화
                from app.agent.service import AnswerService
                app.state.answers = await AnswerService.start()
            try:
                yield
            finally:
                if app.state.answers:
                    await app.state.answers.close()
    #M2, M3 -> 이렇게 분리한 이유는 장애 조회 기능만 실행하거나 RAG 기능과 티켓 실행 기능을 선택적으로 활성화할 수 있도록 하기 위함.
    app = FastAPI(title="기업 업무 대응 AI · M1 조회 API", lifespan=lifespan) 

    #요청 추적
    @app.middleware("http") #Middleware : API의 개별 처리 함수에 들어가기 전과 응답이 나가기 전에 공통으로 실행되는 코드
    async def trace(request: Request, call_next):
        #요청에 유효한 X-Request-ID가 있다면 사용하고, 없다면 UUID를 새로 생성
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = incoming if re.fullmatch(r"[A-Za-z0-9-]{1,64}", incoming) else str(uuid.uuid4())
        
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id

        #정보를 로그에 기록 (요청 발생 시간, 서비스, 요청 ID, HTTP 메서드, 응답 상태, 처리 시간)
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

    #사용자 인증
    def identity(request: Request):
        #HTTP 헤더에서 Bearer 토큰을 추출 (이 토큰을 소지(Bearer)한 사람에게 리소스에 접근할 권한을 준다"는 의미를 가진 HTTP 인증 방식 및 액세스 토큰)
        authorization = request.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        conf = request.app.state.settings

        #이후 서버에 설정된 토큰과 비교
        for expected, user, role in [
            (conf.viewer_token, "demo-viewer", "viewer"),
            (conf.operator_token, "demo-operator", "operator")
        ]:
            if hmac.compare_digest(token.encode(), expected.encode()):
                return user, role #인증에 성공하면 사용자 ID와 권환을 반환
        raise ApiError(401, "UNAUTHENTICATED", "인증이 필요합니다.")

    #조회 요청 검증
    #Depends(identity)는 FastAPI의 의존성 주입 기능 -> 해당 API가 실행되기 전에 identity()를 호출하여 인증을 수행
    def query(request: Request, principal=Depends(identity)): 
        #동일한 조회 조건이 중복 전달되는 것을 막음 
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
        tickets = request.app.state.tickets
        ticket_ready = await tickets.ready() if tickets else True
        complete = healthy and (rag_ready if answers else True) and ticket_ready
        return JSONResponse(status_code=200 if complete else 503, content={
            "status": "UP" if complete else "DOWN", "stage": "M3" if tickets else "M2" if answers else "M1",
            "agent_db": ("UP" if ticket_ready else "DOWN") if tickets else "NOT_ENABLED",
            "business": "UP" if healthy else "DOWN",
            "rag": ("UP" if rag_ready else "DOWN") if answers else "NOT_IMPLEMENTED"
        })

    #실제 장애 조회 API -> 사용자가 장애 조회를 요청하면 실행
    @app.get("/v1/incidents", response_model=IncidentPage)
    async def incidents(request: Request, filters: Annotated[IncidentQuery, Depends(query)],
                        principal=Depends(identity)):
        user, role = principal
        headers = {
            "Authorization": "Bearer " + request.app.state.settings.business_service_token,
            "X-User-ID": user, "X-User-Role": role,
            "X-Request-ID": request.state.request_id
        }
        for attempt in range(3): #조회 요청 재시도(최대 3번)
            try:
                #여기서 FastAPI가 DB를 직접 조회하는 것은 아님
                #FastAPI가 조회 조건을 검사한 뒤 Spring Boot의 /api/vi/incidents API를 호출
                #model_dump()는 Pydantic 객체를 전달 가능한 데이터로 변환
                #by_alias=True는 from_time을 API 필드명인 from으로 변환
                #exclude_none=True는 지정하지 않은 선택 조건을 제외
                response = await request.app.state.client.get(
                    "/api/v1/incidents",
                    params=filters.model_dump(mode="json", by_alias=True, exclude_none=True), 
                    headers=headers
                )
                #알사적인 서버 오류가 발생하면 잠깐 대기한 뒤 다시 요청
                if response.status_code in {502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.1 * (2 ** attempt)) #이때 대기 시간을 점차 늘리는 방식 -> Exponential Backoff(지수 백오프)
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

    #RAG 답변 생성
    @app.post("/v1/answers")
    async def answer(request: Request, payload: AnswerRequest, principal=Depends(identity)):
        runtime = request.app.state.answers
        if runtime is None:
            raise ApiError(503, "RAG_NOT_ENABLED", "문서 검색 기능이 아직 준비되지 않았습니다.")
        async def business_reader():
            page = await incidents(request, payload.incident_filters, principal)
            return page.model_dump(mode="json")
        try:
            #여기서 실제 RAG 로직은 AnswerService의 run() 메서드에 위임
            #payload.incident_filters가 있으면 business_reader()를 전달하여 장애 데이터 조회를 함께 수행할 수 있도록 합니다.
            #ai-service/app/agent/service.py의 AnswerService클래스의 run() 메서드
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

    app.include_router(approval_router(identity, ApiError))
    app.include_router(ticket_runs_router(identity, ApiError))
    app.include_router(draft_preview_router(identity, incidents, ApiError))
    return app


app = create_app()
