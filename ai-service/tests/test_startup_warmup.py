"""기동 워밍업은 LLM을 호출하지 않고 검색 실패를 숨기지 않습니다."""
import asyncio
from unittest.mock import Mock

import pytest

from app.agent import service
from app.rag.store import RagUnavailable


@pytest.mark.parametrize("enabled", [True, False])
def test_optional_startup_warmup_uses_only_synthetic_search(monkeypatch, enabled):
    store = Mock()
    monkeypatch.setattr(service.RagStore, "from_env", lambda: store)
    monkeypatch.setattr(service, "build_graph", Mock())
    monkeypatch.setenv("LLM_MODE", "extractive")
    monkeypatch.setenv("RAG_WARMUP", str(enabled).lower())
    http = Mock(side_effect=AssertionError("LLM must not be called"))
    monkeypatch.setattr(service.httpx, "AsyncClient", http)
    runtime = asyncio.run(service.AnswerService.start())
    assert runtime.store is store
    if enabled:
        store.search.assert_called_once_with("운영 매뉴얼 점검 절차", "viewer")
    else:
        store.search.assert_not_called()
    http.assert_not_called()


def test_warmup_failure_prevents_service_start(monkeypatch):
    store = Mock()
    store.search.side_effect = RagUnavailable("unavailable")
    monkeypatch.setattr(service.RagStore, "from_env", lambda: store)
    graph = Mock()
    monkeypatch.setattr(service, "build_graph", graph)
    monkeypatch.setenv("RAG_WARMUP", "true")
    with pytest.raises(RagUnavailable):
        asyncio.run(service.AnswerService.start())
    graph.assert_not_called()
