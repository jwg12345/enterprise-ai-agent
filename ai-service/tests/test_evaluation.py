"""평가기가 잘못된 응답을 통과시키거나 미실행 분모를 숨기지 않는지 검사."""
import importlib.util
import json
from pathlib import Path
from urllib.error import URLError

import pytest


spec = importlib.util.spec_from_file_location(
    "evaluate_m2", Path(__file__).resolve().parents[2] / "scripts" / "evaluate_m2.py"
)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


@pytest.mark.parametrize("invalid", ["source_ids", "steps", "answer"])
def test_reject_invalid_answer(monkeypatch, invalid):
    response = {"abstain": False, "answer": "합성 답변", "source_ids": ["chunk-1"],
                "citations": [{"document_id": "network-operations", "chunk_id": "chunk-1"}],
                "steps": [{"node": "retrieve_manual"}]}
    monkeypatch.setattr(evaluation, "request_json", lambda *args: (200, response, 1))
    case = evaluation.load_cases()[0]
    assert evaluation.evaluate_case(case)["passed"]
    response[invalid] = {"source_ids": ["invented"], "steps": ["retrieve_manual", "create_ticket"],
                         "answer": ""}[invalid]
    assert not evaluation.evaluate_case(case)["passed"]


def test_mid_run_failure_preserves_denominator(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "RESULTS", tmp_path)
    monkeypatch.setattr(evaluation, "load_env", lambda: None)
    monkeypatch.setattr(evaluation, "request_json", lambda *args: (200, {"stage": "M2", "rag": "UP"}, 1))
    calls = []

    def answer(case):
        if calls:
            raise URLError("secret must not be saved")
        calls.append(case)
        return {"id": case["id"], "passed": True}

    monkeypatch.setattr(evaluation, "evaluate_case", answer)
    assert evaluation.main() == 1
    report = (tmp_path / "m2-latest.json").read_text(encoding="utf-8")
    assert json.loads(report)["summary"] == {
        "passed": 1, "total": 3, "completed": 1, "error": "URLError"
    }
    assert "secret" not in report


def test_same_document_wrong_section_is_failure(monkeypatch):
    case = {"query": "합성 질문", "id": "rag-section", "expected_sources": ["incident-policy"],
            "expected_sections": [{"document_id": "incident-policy", "section": "승인과 감사"}],
            "expected_tools": ["retrieve_manual"], "expected_behavior": "cited_answer"}
    response = {"abstain": False, "answer": "합성 답변", "source_ids": ["c"],
                "steps": ["retrieve_manual"], "citations": [
                    {"document_id": "incident-policy", "chunk_id": "c", "section": "상태와 기록"}]}
    monkeypatch.setattr(evaluation, "request_json", lambda *args: (200, response, 1))
    assert not evaluation.evaluate_case(case)["checks"]["sections"]


def test_quality_datasets_are_disjoint_and_grounded(monkeypatch):
    sets = []
    for split, count in [("dev", 10), ("fixed", 30)]:
        monkeypatch.setattr(evaluation, "DATASET", evaluation.ROOT / "eval" / f"rag-{split}.jsonl")
        cases = evaluation.load_cases()
        assert len(cases) == count
        assert len({c["id"] for c in cases}) == count
        for case in cases:
            for expected in case["expected_sections"]:
                manuals = list((evaluation.ROOT / "data/manuals").glob("*.md"))
                assert any(f'document_id: {expected["document_id"]}' in p.read_text(encoding="utf-8")
                           and f'## {expected["section"]}' in p.read_text(encoding="utf-8") for p in manuals)
        sets.append({c["query"] for c in cases})
    assert not sets[0] & sets[1]
