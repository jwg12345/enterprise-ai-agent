"""평가 실패가 보류 성공으로 집계되거나 근거 없는 응답이 통과하지 않도록 검사합니다."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from urllib.error import HTTPError, URLError

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/evaluate_m4.py"
spec = importlib.util.spec_from_file_location("evaluate_m4", SCRIPT)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


@pytest.mark.parametrize("exc,expected", [(TimeoutError("secret"), "client_timeout"),
    (URLError(TimeoutError("secret")), "client_timeout"), (ValueError("secret"), "invalid_json"),
    (ConnectionRefusedError("secret"), "connection_error")])
def test_transport_errors_are_distinct_without_raw_details(exc, expected):
    assert evaluation.transport_error(exc) == expected


def test_server_failure_stops_calls_and_preserves_planned_denominator(tmp_path, monkeypatch):
    (tmp_path / "eval").mkdir()
    (tmp_path / "data/manuals").mkdir(parents=True)
    (tmp_path / ".env").write_text("DEMO_VIEWER_TOKEN=fake-test-token\n", encoding="utf-8")
    cases = [{"id": str(i), "kind": "answer", "expected": "answer", "query": "점검", "review": "근거"} for i in range(2)]
    (tmp_path / "eval/m4-quality.jsonl").write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["evaluate_m4", "--execute"])
    calls = []
    def open_request(request, **kwargs):
        calls.append(request)
        raise HTTPError(request.full_url, 503, "sensitive-detail", {}, None)
    monkeypatch.setattr(evaluation, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    assert evaluation.main() == 1 and len(calls) == 1
    text = next((tmp_path / "eval/results").glob("*.json")).read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["planned"] == 2 and report["completed"] == 1 and report["contract_passed"] == 0
    assert report["cases"][0]["error_kind"] == "http_error"
    assert "fake-test-token" not in text and "sensitive-detail" not in text


@pytest.mark.parametrize("status,data", [(502, {}), (0, {}), (200, []), (200, {"mode": "compatible", "abstain": "true"})])
def test_errors_and_invalid_abstentions_fail(status, data):
    assert not all(evaluation.assess({"kind": "answer", "expected": "abstain"}, status, data).values())


@pytest.mark.parametrize("patch", [{"source_ids": ["unknown"]}, {"citations": []}, {"answer": " "}, {"citations": [None]}])
def test_answer_requires_real_text_and_matching_sources(patch):
    data = {"mode": "compatible", "abstain": False, "answer": "점검 요청", "source_ids": ["c1"], "citations": [{"chunk_id": "c1"}]}
    case = {"kind": "answer", "expected": "answer"}
    assert all(evaluation.assess(case, 200, data).values())
    assert not all(evaluation.assess(case, 200, {**data, **patch}).values())


def test_wrong_incident_and_abstention_with_draft_fail():
    data = {"mode": "llm_preview", "abstain": False, "citations": [{"chunk_id": "c1"}],
            "draft": {"incident_id": "INC-014", "priority": "P1", "team": "Platform", "title": "점검", "body": "기록"}}
    case = {"kind": "draft", "expected": "answer"}
    assert all(evaluation.assess(case, 200, data).values())
    data["draft"]["incident_id"] = "INC-other"
    assert not all(evaluation.assess(case, 200, data).values())
    data["abstain"] = True
    assert not all(evaluation.assess({"kind": "draft", "expected": "abstain"}, 200, data).values())
