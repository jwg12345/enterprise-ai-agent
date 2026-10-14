"""인증된 실행 계층: 업무 쓰기는 Spring, 실행 소유권과 체크포인트는 agent DB."""
#AI가 작성한 점검 요청서 초안을 Spring Boot에 업무 시스템에 전달하고, 사람의 승인 여부에 따라 티켓이 생성되도록 실행 과정을 관리
import hashlib
import asyncio
import json
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.approvals import Approval, Ticket, CONFLICTS
from app.agent.checkpoints import open_checkpointer
from app.agent.ticket_graph import build_ticket_graph, LedgerMismatch


class RunError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code

#Spring Boot의 승인, 티켓 API 통신 (Spring Boot와 통신)
class SpringLedger: #객체를 만들 때 HTTP 클라이언트와 인증 정보 전달
    def __init__(self, client, token, owner, trace):
        self.client = client
        self.headers = {"Authorization": "Bearer " + token, "X-User-ID": owner,
                        "X-User-Role": "operator", "X-Request-ID": trace} #서비스 인증 토큰, 요청한 사용자, 사용자 역할, 요청 추적 ID
        self.owner = owner

    # HTTP 요청을 보내는 공통 함수
    #method:GET, POST / path:호출할 API 주소 / payload:Spring Boot에 전달할 JSON 데이터 / model:API 응답을 검증할 Pydantic 모델
    async def request(self, method, path, model, payload=None, key=None):
        headers = dict(self.headers)

        #멱등키를 HTTP 헤더에 추가하는 코드(중복 생성 방지할 수 있도록 함, 이 코드가 중복을 직접 막는 부분은 아님)
        #실제 중복 생성 방지는 Spring Boot 측에서 담당
        if key:
            headers["Idempotency-Key"] = key
            
        try:
            response = await self.client.request(method, path, headers=headers, json=payload)
        except httpx.HTTPError:
            raise RunError(503, "RECONCILING") from None
        if response.status_code not in {200, 201}:
            code = "BUSINESS_UNAVAILABLE"
            try:
                candidate = response.json()["error"]["code"]
                if isinstance(candidate, str) and candidate in CONFLICTS:
                    code = candidate
            except (ValueError, KeyError, TypeError):
                pass
            raise RunError(response.status_code if response.status_code in {403, 404, 409, 422} else 503, code)
        try:
            result = model.model_validate(response.json()).model_dump(mode="json")
            if model is Approval and result["owner_id"] != self.owner:
                raise ValueError("owner")
            return result
        except (ValueError, ValidationError):
            raise RunError(502, "INVALID_BUSINESS_RESPONSE") from None

    #승인 요청 생성
    async def propose(self, run_id, owner_id, draft):
        return await self.request("POST", "/api/v1/approvals", Approval,
                                  {"run_id": run_id, "proposal_version": 1, "draft": draft})
    #승인 원장 조회
    async def get(self, approval_id, owner_id):
        return await self.request("GET", "/api/v1/approvals/" + approval_id, Approval)
        
    #승인 또는 거절 결정 등록
    async def decide(self, approval_id, decision):
        return await self.request("POST", "/api/v1/approvals/" + approval_id + "/decision", Approval,
                                  {"decision": decision})

    #최종 티켓 생성 
    async def create_ticket(self, approval_id, draft_hash, owner_id, key):
        return await self.request("POST", "/api/v1/tickets", Ticket,
                                  {"approval_id": approval_id, "draft_hash": draft_hash}, key)

#실행 기록, 사용자 소유권, 중복 요청, 체크포인트 및 그래프 실행 관리(실행 상태 관리)
class TicketRuntime:
    def __init__(self, client, token):
        self.client, self.token = client, token
    
    #실행 기록 테이블 생성
    async def setup(self):
        async with open_checkpointer() as saver: #PostgreSQL에 연결
            await saver.conn.execute("SELECT pg_advisory_lock(7303002)")
            try: #테이블 생성 -> (이 테이블은 에이전트의 실행 기록을 저장)
                await saver.conn.execute("""CREATE TABLE IF NOT EXISTS agent.ticket_runs (
                    run_id uuid PRIMARY KEY, owner_id text NOT NULL, request_key varchar(128) NOT NULL,
                    draft_hash char(64) NOT NULL, draft_json jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(owner_id, request_key))""")
            finally:
                await saver.conn.execute("SELECT pg_advisory_unlock(7303002)")

    #서비스 준비 상태 확인
    #PostgreSQL 연결과 실행 기록 테이블 조회가 가능한지 검사
    #LIMIT=0이므로 실제 데이터를 가져오지 않고 테이블에 접근할 수 있는지 확인
    async def ready(self):
        try:
            async with asyncio.timeout(3):
                async with open_checkpointer(initialize=False) as saver:
                    await saver.conn.execute("SELECT run_id FROM agent.ticket_runs LIMIT 0")
                    return True
        except Exception:
            return False

    #사용자별 실행 기록 조회
    #현재 사용자의실행 기록을 최신순으로 최대 20개 가져옴
    async def list_runs(self, owner):
        async with open_checkpointer(initialize=False) as saver:
            cursor = await saver.conn.execute(
                "SELECT run_id,created_at FROM agent.ticket_runs WHERE owner_id=%s ORDER BY created_at DESC LIMIT 20",
                (owner,))
            return {"items": [{"run_id": str(r["run_id"]), "created_at": r["created_at"].isoformat()}
                              for r in await cursor.fetchall()]}

    #실행을 새로 시작하거나 기존 실행을 조회하고, 승인 결정에 따라 중단된 그래프를 재개하는 함수
    async def operate(self, owner, trace, run_id=None, draft=None, key=None, action="get", decision=None, approval_id=None):
        from langgraph.types import Command

        async with open_checkpointer(initialize=False) as saver:
            conn = saver.conn
            if draft is not None: #새로운 초안을 등록할 떄
                #초안 데이터를 정해진 JSON 형식으로 변환
                encoded = json.dumps(draft, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                #초안의 SHA-256 해시를 생성
                digest = hashlib.sha256(encoded.encode()).hexdigest()
                #실행 기록을 PostgreSQL에 저장 / ON CONFLICT ... DO NOTHING 때문에 같은 사용자와 같은 요청 키로 중복 등록하면 새 실행 기록을 생성하지 않음
                #UNIQUE(owner_id, request_key) -> 테이블 생성 때 설정한 DB 제약
                # | owner_id | request_key | 저장 가능? |
                # |--------|-------|----------------|
                # | user-A | key-1 | 처음이므로 가능 |
                # | user-A | key-1 | 같은 조합이므로 불가능 |
                # | user-A | key-2 | 다른 키이므로 가능 |
                # | user-B | key-1 | 다른 사용자이므로 가능 |
                #ON CONFLICT(owner_id, request_key) DO NOTHING -> 같은 사용자·요청 키가 이미 있어서 UNIQUE 제약과 충돌하면, 새 행을 넣지 말고 넘어가라
                await conn.execute("""INSERT INTO agent.ticket_runs(run_id,owner_id,request_key,draft_hash,draft_json)
                    VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT(owner_id,request_key) DO NOTHING""",
                    (uuid4(), owner, key, digest, encoded))
                cursor = await conn.execute("SELECT * FROM agent.ticket_runs WHERE owner_id=%s AND request_key=%s", (owner, key))
                row = await cursor.fetchone()
                #저장된 초안 해시가 요청한 초안읜 해시와 같은지 비교
                if row["draft_hash"] != digest:
                    raise RunError(409, "IDEMPOTENCY_CONFLICT")
                run_id = str(row["run_id"])
            else: #기존 실행을 조회할 때
                #기존 작업을 조회할 때는 run_id와 owner_id를 함께 조건으로 사용
                #다른 사람의 run_id를 알고 있더라도 자신의 실행 기록이 아니면 조회하지 못하도록 하는 구조
                cursor = await conn.execute("SELECT * FROM agent.ticket_runs WHERE run_id=%s AND owner_id=%s", (run_id, owner))
                row = await cursor.fetchone()
                if row is None: #조회결과가 없으면
                    raise RunError(404, "NOT_FOUND")
            # pg_try_advisory_lock() -> PostgreSQL의 Advisory Lock을 이용해 동일한 실행에 대해 여러 요청이 동시에 처리되는 것을 방지
            lock = await conn.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired", ("run:" + run_id,))
            if not (await lock.fetchone())["acquired"]:
                raise RunError(409, "RUN_BUSY")
            try: #승인 또는 거절 이후 재개할 때
                #그래프 구성
                ledger = SpringLedger(self.client, self.token, owner, trace)
                graph = build_ticket_graph(ledger, saver)

                #실행에 대응하는 thread_id 지정
                config = {"configurable": {"thread_id": "ticket-run:" + run_id}, "recursion_limit": 12}
                #LangGraph는 이 thread_id를 사용해 PostgreSQL에 저장된 체크포인트 식별
                #이 때, snapshot은 해당 실행이 어느 상태에서 중단되었는지 등의 정보를 담고 있음
                snapshot = await graph.aget_state(config)
                if action != "get": 
                    if not snapshot.values:
                        if action == "decision":
                            raise RunError(409, "APPROVAL_NOT_READY")
                        await graph.ainvoke({"run_id": run_id, "owner_id": owner, "draft": row["draft_json"]}, config)
                    else:
                        state = snapshot.values
                        if action == "decision": #승인 결정이 들어오면
                            if approval_id != state.get("approval_id"): #승인 ID가 현재 실행 상태의 승인 ID와 같은지 확인하고 Spring Boot에 승인 또는 거절 결정을 기록
                                raise RunError(409, "APPROVAL_MISMATCH")
                            await ledger.decide(approval_id, decision)
                        if snapshot.next:
                            interrupted = any(task.interrupts for task in snapshot.tasks)
                            await graph.ainvoke(Command(resume="wake") if interrupted else None, config) # Command(resume="wake")는 중단된 LangGraph 실행을 다시 시작하라는 명령
                    snapshot = await graph.aget_state(config)
                state = snapshot.values
                approval = await ledger.get(state["approval_id"], owner) if state.get("approval_id") else None
                status = {"PENDING": "WAITING_APPROVAL", "APPROVED": "RECONCILING", "EXECUTED": "COMPLETED",
                          "REJECTED": "REJECTED", "EXPIRED": "EXPIRED"}.get(approval["status"] if approval else "", "RUNNING")
                return {"run_id": run_id, "status": status, "approval": approval,
                        "ticket_id": approval.get("ticket_id") if approval else None}
            except LedgerMismatch:
                raise RunError(409, "LEDGER_MISMATCH") from None
            finally: #그래프 실행이 끝나면 잠금을 해제합니다. 참고로 이 잠금은 같은 run_id의 동시 실행을 막는 것이고, 같은 티켓이 중복 생성되는 것을 방지하는 최종 수단은 아닙니다
                await conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", ("run:" + run_id,))
