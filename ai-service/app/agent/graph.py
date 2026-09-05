import asyncio
import time
from typing import TypedDict
from app.agent.answers import guard


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


class AnswerNodes:
    def __init__(self, retriever, generator, business_reader=None):
        self.retriever, self.generator = retriever, generator
        self.business_reader = business_reader

    async def route(self, state):
        return {"route": guard(state["query"]), "steps": ["guard"]}

    async def business(self, state):
        incidents = await self.business_reader() if self.business_reader else None
        return {'incidents': incidents, 'steps': state['steps'] + (['search_incidents'] if incidents is not None else [])}

    async def retrieve(self, state):
        started = time.monotonic()
        citations = await asyncio.to_thread(self.retriever.search, state["query"], state["role"])
        return {"citations": citations, "steps": state["steps"] + [
            {"node": "retrieve_manual", "duration_ms": round((time.monotonic() - started) * 1000)}
        ]}

    async def answer(self, state):
        result = await self.generator.generate(state["query"], state["citations"], state.get("incidents"))
        return {**result.model_dump(), "steps": state["steps"] + ["answer"]}

    async def decline(self, state):
        message = ("허용되지 않은 작업 요청입니다." if state["route"] == "DENIED"
                   else "티켓 생성과 시스템 변경은 아직 지원하지 않습니다. 문서 조회만 요청해 주세요.")
        return {"answer": message, "source_ids": [], "citations": [], "abstain": True,
                "steps": state["steps"] + ["decline"]}


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
    )
    graph.add_edge("load_incidents", "search_manual")
    graph.add_edge("search_manual", "generate_answer")
    graph.add_edge("generate_answer", END)
    graph.add_edge("decline_request", END)
    return graph.compile()
