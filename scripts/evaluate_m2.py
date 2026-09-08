"""Run the small M2 answer evaluation set against a live local AI service."""

from __future__ import annotations

import json
import argparse
import hashlib
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval" / "dataset.jsonl"
RESULTS = ROOT / "eval" / "results"
API = os.environ.get("AI_API_URL", "http://127.0.0.1:8000").rstrip("/")


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def request_json(path: str, payload: dict | None = None) -> tuple[int, dict, int]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    token = os.environ.get("DEMO_VIEWER_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(API + path, data=body, headers=headers, method="POST" if payload else "GET")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=70) as response:
            elapsed = round((time.monotonic() - started) * 1000)
            return response.status, json.loads(response.read().decode("utf-8")), elapsed
    except urllib.error.HTTPError as exc:
        elapsed = round((time.monotonic() - started) * 1000)
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except ValueError:
            data = {"error": {"code": "NON_JSON_ERROR"}}
        return exc.code, data, elapsed


def load_cases() -> list[dict]:
    cases = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            if case["id"].startswith("rag-") or case["id"] == "guard-01":
                cases.append(case)
    return cases


def evaluate_case(case: dict) -> dict:
    status, data, elapsed = request_json("/v1/answers", {"query": case["query"]})
    source_ids = {item.get("document_id") for item in data.get("citations", [])}
    steps = data.get("steps", [])
    step_names = {step.get("node") if isinstance(step, dict) else step for step in steps}
    expected_sources = set(case.get("expected_sources", []))
    expected_tools = set(case.get("expected_tools", []))
    expected_behavior = case.get("expected_behavior")

    checks = {
        "http_200": status == 200,
        "sources": expected_sources <= source_ids,
        "tools": expected_tools == step_names & {
            "retrieve_manual", "search_incidents", "propose_ticket", "create_ticket"
        },
        "citation_ids": set(data.get("source_ids", [])) <= {
            item.get("chunk_id") for item in data.get("citations", [])
        },
    }
    if case.get("expected_sections"):
        actual_sections = {(item.get("document_id"), item.get("section"))
                           for item in data.get("citations", [])}
        checks["sections"] = all((item["document_id"], item["section"]) in actual_sections
                                 for item in case["expected_sections"])
    if expected_behavior == "abstain":
        checks["abstain"] = data.get("abstain") is True
        if case.get("require_empty_citations", "expected_sections" not in case):
            checks["empty_citations"] = not data.get("citations")
    elif expected_behavior == "deny":
        checks["deny"] = data.get("abstain") is True and not data.get("citations") and "decline" in step_names
    elif expected_behavior == "cited_answer":
        checks["cited_answer"] = (
            data.get("abstain") is False and bool(data.get("citations"))
            and bool(data.get("source_ids")) and bool(data.get("answer", "").strip())
        )

    return {
        "id": case["id"],
        "query": case["query"],
        "expected_behavior": expected_behavior,
        "passed": all(checks.values()),
        "checks": checks,
        "status": status,
        "duration_ms": elapsed,
        "mode": data.get("mode"),
        "prompt_version": data.get("prompt_version"),
        "abstain": data.get("abstain"),
        "sources": sorted(item for item in source_ids if item),
        "retrieved": [{key: item.get(key) for key in (
            "document_id", "section", "chunk_id", "distance", "index_version"
        )} for item in data.get("citations", [])],
        "request_id": data.get("request_id"),
        "error_code": data.get("error", {}).get("code"),
    }


def main() -> int:
    global API
    load_env()
    API = os.environ.get("AI_API_URL", "http://127.0.0.1:8000").rstrip("/")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cases = load_cases()
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    results = {
        "run_id": run_id, "cases": [], "summary": {},
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "git_commit": revision.stdout.strip() if revision.returncode == 0 else None,
        "environment": {"python": platform.python_version(), "os": platform.system()},
        "dataset": DATASET.name,
        "limitations": ["선택한 합성 질문셋의 API 계약 검사이며 일반 정확도 지표가 아님",
                       "DB 쓰기 건수·주장 근거 충실도·검색 임계값 보정은 검증하지 않음",
                       "실제 서버의 모델·인덱스 버전은 이 보고서에서 확인하지 못함"],
    }
    try:
        ready_status, ready, ready_ms = request_json("/health/ready")
        results["ready"] = {"status": ready_status, "body": ready, "duration_ms": ready_ms}
        if ready_status != 200 or ready.get("stage") != "M2" or ready.get("rag") != "UP":
            results["summary"] = {"passed": 0, "total": len(cases), "completed": 0,
                                  "error": "M2 service is not ready"}
            return write_results(results, success=False)
        for case in cases:
            results["cases"].append(evaluate_case(case))
            item = results["cases"][-1]
            print(f"{len(results['cases'])}/{len(cases)} {item['id']}: "
                  f"{'PASS' if item['passed'] else 'FAIL'}", flush=True)
        passed = sum(1 for item in results["cases"] if item["passed"])
        results["summary"] = {"passed": passed, "total": len(cases), "completed": len(results["cases"])}
        results["by_behavior"] = {
            behavior: {"total": sum(c["expected_behavior"] == behavior for c in cases),
                       "passed": sum(r["passed"] for r in results["cases"]
                                     if r["expected_behavior"] == behavior)}
            for behavior in sorted({c["expected_behavior"] for c in cases})
        }
        return write_results(results, success=bool(cases) and passed == len(cases))
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        results["summary"] = {"passed": sum(item["passed"] for item in results["cases"]),
                              "total": len(cases), "completed": len(results["cases"]),
                              "error": type(exc).__name__}
        return write_results(results, success=False)


def write_results(results: dict, success: bool) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    label = "" if DATASET.name == "dataset.jsonl" else DATASET.stem + "-"
    target = RESULTS / f"m2-{label}{results['run_id']}.json"
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = RESULTS / f"m2-{label}latest.json"
    latest.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    summary = results["summary"]
    if "error" in summary:
        print(f"FAIL: {summary['error']} - wrote {target}")
    else:
        print(f"{'PASS' if success else 'FAIL'}: {summary['passed']}/{summary['total']} cases - wrote {target}")
    return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="합성 질문셋 실제 API 평가")
    parser.add_argument("--split", choices=["smoke", "dev", "fixed"], default="smoke")
    args = parser.parse_args()
    if args.split != "smoke":
        DATASET = ROOT / "eval" / f"rag-{args.split}.jsonl"
    raise SystemExit(main())
