import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess

spec = importlib.util.spec_from_file_location(
    "calibrate_rag", Path(__file__).resolve().parents[2] / "scripts/calibrate_rag.py"
)
calibration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calibration)


def rows(positive, negative):
    return [{"expected_sections": [{"document_id": "m", "section": "s"}],
             "candidates": [{"document_id": "m", "section": "s", "distance": positive}]},
            {"expected_sections": [], "candidates": [
                {"document_id": "m", "section": "s", "distance": negative}]}]


def test_boundary_is_inclusive_and_no_rounding():
    result = calibration.propose(rows(0.456789123, 0.5))
    assert result["recommended"]["threshold"] == 0.456789123
    assert result["recommended"]["positive_hits"] == 1
    assert result["recommended"]["negative_false_retrievals"] == 0
    assert result["baseline_0_45"]["positive_hits"] == 0


def test_overlapping_distances_do_not_propose_false_success():
    assert calibration.propose(rows(0.6, 0.5))["recommended"] is None
    assert calibration.propose(rows(0.5, 0.5))["recommended"] is None


def test_worker_failure_still_restores_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(calibration, "ROOT", tmp_path)
    calls = []

    def docker(*args):
        calls.append(args)
        return CompletedProcess(args, 1 if args[0] == "run" else 0,
                                stdout="ai\nchroma\n" if args[0] == "ps" else "", stderr="")

    monkeypatch.setattr(calibration, "docker", docker)
    assert calibration.main() == 1
    assert calls[-1][0] == "start"
    report = json.loads(next((tmp_path / "eval/results").glob("*.json")).read_text(encoding="utf-8"))
    assert report["ai_restored"] is True
    assert report["error"] == "distance_worker_failed"


def test_access_denial_does_not_stop_services(monkeypatch):
    calls = []

    def docker(*args):
        calls.append(args)
        return CompletedProcess(args, 1, stdout="", stderr="denied")

    monkeypatch.setattr(calibration, "docker", docker)
    assert calibration.main() == 1
    assert len(calls) == 1 and calls[0][0] == "ps"


def test_diagnostic_keeps_controls_and_only_selects_known_misses():
    dev = [json.loads(line) for line in (calibration.ROOT / "eval/rag-dev.jsonl").read_text(encoding="utf-8").splitlines()]
    fixed = [json.loads(line) for line in (calibration.ROOT / "eval/rag-fixed.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = calibration.diagnostic_cases(dev, fixed)
    assert len(cases) == 24
    for variant in ["original", "context"]:
        selected = [c for c in cases if c["variant"] == variant]
        assert len(selected) == 12
        assert sum(not c["expected_sections"] for c in selected) == 4
        assert {c["id"] for c in selected if c["id"].startswith("rag-fixed")} == {"rag-fixed-05", "rag-fixed-12"}
    assert all(c["search_query"] == c["query"] for c in cases if c["variant"] == "original")
    assert all(c["search_query"] == "사내 IT 장애 운영 매뉴얼: " + c["query"]
               for c in cases if c["variant"] == "context")
