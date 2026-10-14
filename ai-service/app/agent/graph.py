#운영 매뉴얼 질의응답 LangGraph (guardrails.py, RagStore, answer.py 연결)
import asyncio
import time
from typing import TypedDict
from app.agent.answers import guard

#그래프의 공유 상태
class State(TypedDict, total=False):
    query: str
    role: str
    request_id: str
    route: str
    citations: list
    answer: str
    source_ids: list
    abstain: bool
    steps: list
    incidents: dict | None

#그래프의 개별 실행
class AnswerNodes:
    def __init__(self, retriever, generator, business_reader=None):
        self.retriever, self.generator = retriever, generator #RagStore 검색 객체, AnswerGenerator 답변 생성 객체
        self.business_reader = business_reader #선택적인 장애 기록 조회

    async def route(self, state): # 사용자 질문 검색
        return {"route": guard(state["query"]), "steps": ["guard"]}

    async def business(self, state): #장애 데이터 조회
        incidents = await self.business_reader() if self.business_reader else None
        return {'incidents': incidents, 'steps': state['steps'] + (['search_incidents'] if incidents is not None else [])}

    async def retrieve(self, state): #RAG 검색 수행
        started = time.monotonic()
        citations = await asyncio.to_thread(self.retriever.search, state["query"], state["role"])
        return {"citations": citations, "steps": state["steps"] + [
            {"node": "retrieve_manual", "duration_ms": round((time.monotonic() - started) * 1000)}
        ]} 
        #asyncio.to_thread
        #BGE-M3의 CPU 임베딩과 ChromaDB 동기 검색 호출을 별도 스레드에서 실행해, 비동기 이벤트 루프가 해당 동기 작업 때문에 직접 막히지 않게 합니다.

    #검색 결과로 답변을 생성
    async def answer(self, state):
        result = await self.generator.generate(state["query"], state["citations"], state.get("incidents"))
        return {**result.model_dump(), "steps": state["steps"] + ["answer"]}

    #허용되지 않는 요청에 안내 메시지 반환
    async def decline(self, state):
        message = ("허용되지 않은 작업 요청입니다." if state["route"] == "DENIED"
                   else "티켓 생성과 시스템 변경은 아직 지원하지 않습니다. 문서 조회만 요청해 주세요.")
        return {"answer": message, "source_ids": [], "citations": [], "abstain": True,
                "steps": state["steps"] + ["decline"]}

#그래프 연결
def build_graph(retriever, generator, business_reader=None):
    from langgraph.graph import END, START, StateGraph

    nodes = AnswerNodes(retriever, generator, business_reader)
    graph = StateGraph(State)
    for name, handler in {
        "validate_input": nodes.route, "load_incidents": nodes.business,
        "search_manual": nodes.retrieve, "generate_answer": nodes.answer,
        "decline_request": nodes.decline
    }.items():
        graph.add_node(name, handler)
    graph.add_edge(START, "validate_input")
    graph.add_conditional_edges(
        "validate_input", lambda state: "read" if state["route"] == "READ" else "decline",
        {"read": "load_incidents", "decline": "decline_request"}
    ) #사용자의 질문이 'READ'로 분류되면 검색 흐름을 진행하고, 그 외에는 거절노드로 이동
    graph.add_edge("load_incidents", "search_manual")
    graph.add_edge("search_manual", "generate_answer")
    graph.add_edge("generate_answer", END)
    graph.add_edge("decline_request", END)
    return graph.compile()
