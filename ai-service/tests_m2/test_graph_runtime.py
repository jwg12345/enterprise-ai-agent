"""M2 추가 의존성 설치 후 명시적으로 실행합니다. 모델은 대체하지만 LangGraph는 실제로 실행합니다."""
import asyncio
from unittest.mock import Mock
from app.agent.answers import AnswerGenerator
from app.agent.graph import build_graph


def test_actual_langgraph_routes_and_abstains():
    retriever = Mock()
    retriever.search.return_value = []
    graph = build_graph(retriever, AnswerGenerator())
    result = asyncio.run(graph.ainvoke({"query": "매뉴얼", "role": "viewer", "request_id": "test"}))
    assert result["abstain"]
    retriever.search.assert_called_once_with("매뉴얼", "viewer")


def test_actual_langgraph_blocks_write_before_retrieval():
    retriever = Mock()
    graph = build_graph(retriever, AnswerGenerator())
    result = asyncio.run(graph.ainvoke({"query": "티켓을 생성해", "role": "operator", "request_id": "test"}))
    assert result["abstain"] and result["citations"] == []
    retriever.search.assert_not_called()
