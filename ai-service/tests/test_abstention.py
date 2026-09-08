import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError
from app.agent.answers import AnswerFailure, AnswerGenerator, parse_provider_answer

SOURCE = {"chunk_id": "c1", "text": "합성 운영 매뉴얼"}


@pytest.mark.parametrize("text", ["", "  \n "])
@pytest.mark.parametrize("sources", [[], ["c1"]])
def test_explicit_empty_abstention_has_display_message(text, sources):
    result = parse_provider_answer(json.dumps({"answer": text, "source_ids": sources, "abstain": True}), [SOURCE])
    assert result.abstain and "근거" in result.answer
    assert result.source_ids == sources


@pytest.mark.parametrize("payload", [
    {"answer": "", "source_ids": ["c1"], "abstain": False},
    {"answer": None, "source_ids": [], "abstain": True},
    {"source_ids": [], "abstain": True},
    {"answer": "", "source_ids": [], "abstain": "true"},
])
def test_invalid_outputs_do_not_become_abstentions(payload):
    with pytest.raises(ValidationError):
        parse_provider_answer(json.dumps(payload), [SOURCE])


@pytest.mark.parametrize("sources", [["invented"], ["c1", "c1"]])
def test_abstention_still_rejects_invalid_citations(sources):
    with pytest.raises(AnswerFailure):
        parse_provider_answer(json.dumps({"answer": "", "source_ids": sources, "abstain": True}), [SOURCE])


@pytest.mark.parametrize("status", [429, 500])
def test_provider_failure_is_not_a_successful_abstention(monkeypatch, status):
    monkeypatch.setenv("LLM_MODEL", "test-model")

    async def run():
        async with httpx.AsyncClient(base_url="https://test.invalid/",
                                    transport=httpx.MockTransport(lambda req: httpx.Response(status))) as client:
            with pytest.raises(AnswerFailure):
                await AnswerGenerator("compatible", client).generate("합성 질문", [SOURCE])

    asyncio.run(run())
