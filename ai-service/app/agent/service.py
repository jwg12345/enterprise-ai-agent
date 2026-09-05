import asyncio
import os
from urllib.parse import urlparse

import httpx

from app.agent.answers import AnswerFailure, AnswerGenerator, redact
from app.agent.graph import build_graph
from app.rag.store import RagStore


class AnswerService:
    def __init__(self, store, generator, client=None):
        self.store, self.generator, self.client = store, generator, client

    @classmethod
    async def start(cls):
        store = await asyncio.to_thread(RagStore.from_env)
        mode = os.environ.get("LLM_MODE", "extractive")
        client = None
        if mode == "compatible":
            base = os.environ.get("LLM_BASE_URL", "")
            parsed = urlparse(base)
            local = parsed.hostname in {"localhost", "127.0.0.1", "ollama", "host.docker.internal"}
            if parsed.username or not parsed.hostname or not (parsed.scheme == "https" or (local and parsed.scheme == "http")):
                raise AnswerFailure("LLM_BASE_URL 설정을 확인하세요.")
            if not os.environ.get("LLM_MODEL") or not os.environ.get("LLM_API_KEY"):
                raise AnswerFailure("LLM_MODEL과 LLM_API_KEY를 설정하세요.")
            client = httpx.AsyncClient(base_url=base.rstrip("/") + "/", timeout=30, trust_env=False,
                                       headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
        elif mode != "extractive":
            raise AnswerFailure("지원하지 않는 LLM 모드입니다.")
        # 의존성이 없으면 기동 단계에서 실패하며 가짜 그래프로 대체하지 않습니다.
        build_graph(store, AnswerGenerator(mode, client))
        return cls(store, AnswerGenerator(mode, client), client)

    async def close(self):
        if self.client:
            await self.client.aclose()

    async def ready(self):
        try:
            async with asyncio.timeout(3):
                return await asyncio.to_thread(self.store.ready)
        except TimeoutError:
            return False

    async def run(self, query, role, request_id, business_reader=None):
        graph = build_graph(self.store, self.generator, business_reader)
        async with asyncio.timeout(60):
            result = await graph.ainvoke(
                {"query": redact(query), "role": role, "request_id": request_id},
                config={"recursion_limit": 12}
            )
        return {"request_id": request_id, "answer": result["answer"], "citations": result["citations"],
                "source_ids": result["source_ids"], "abstain": result["abstain"],
                "mode": self.generator.mode, "steps": result["steps"],
                "incidents": result.get("incidents"), "prompt_version": "m2-v1",
                "relevance_threshold_calibrated": False}
