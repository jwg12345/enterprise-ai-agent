"""합성 품질셋의 실제 답변/초안 평가. 티켓 생성·승인·설정 변경은 수행하지 않습니다."""
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]


def transport_error(exc):
    if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
        return "client_timeout"
    if isinstance(exc, ValueError):
        return "invalid_json"
    return "connection_error"


def assess(case, status, data):
    if not isinstance(data, dict):
        return {"http_200": status == 200, "response_object": False}
    draft_mode = case["kind"] == "draft"
    citations = data.get("citations", [])
    checks = {"http_200": status == 200, "mode": data.get("mode") == ("llm_preview" if draft_mode else "compatible")}
    if not isinstance(citations, list) or any(not isinstance(c, dict) or not isinstance(c.get("chunk_id"), str) or not c["chunk_id"] for c in citations):
        return {**checks, "citations_shape": False}
    if case["expected"] == "abstain":
        checks["behavior"] = data.get("abstain") is True and (not draft_mode or data.get("draft") is None)
    else:
        checks["behavior"] = data.get("abstain") is False and bool(data.get("draft") if draft_mode else data.get("answer"))
        checks["evidence_present"] = bool(citations)
        if draft_mode:
            draft = data.get("draft") or {}
            if not isinstance(draft, dict):
                return {**checks, "draft_shape": False}
            checks["incident_binding"] = draft.get("incident_id") == "INC-014" and draft.get("priority") == "P1"
            checks["draft_content"] = all(isinstance(draft.get(k), str) and bool(draft[k].strip()) for k in ("title", "body"))
            checks["team"] = draft.get("team") == "Platform"
        else:
            ids = data.get("source_ids", [])
            checks["answer_text"] = isinstance(data.get("answer"), str) and bool(data["answer"].strip())
            checks["citation_ids"] = isinstance(ids, list) and bool(ids) and all(isinstance(i, str) for i in ids) and set(ids) <= {c["chunk_id"] for c in citations}
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="실제 LLM API 최대 8회 호출")
    parser.add_argument("--dataset", choices=("regression", "acceptance"), default="regression")
    args = parser.parse_args()
    if not args.execute:
        parser.error("실제 LLM 비용이 발생합니다. --execute를 지정하세요.")
    dataset = ROOT / ("eval/m4-acceptance.jsonl" if args.dataset == "acceptance" else "eval/m4-quality.jsonl")
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    sha = hashlib.sha256(dataset.read_bytes()).hexdigest()
    config = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip().strip("\"'")
    folder = ROOT / "eval/results"
    folder.mkdir(parents=True, exist_ok=True)
    previously_used = any(json.loads(p.read_text(encoding="utf-8")).get("dataset_sha256") == sha
                          for p in folder.glob("m4-quality-*.json"))
    report = {"dataset_sha256": sha, "dataset": dataset.name, "client_timeout_seconds": 65,
              "evaluation_role": "regression" if previously_used else "first_observation",
              "planned": len(cases), "cases": [], "python": platform.python_version(),
              "config": {k: config.get(k) for k in ("LLM_MODEL", "RAG_MAX_DISTANCE", "RAG_QUERY_PREFIX", "EMBEDDING_REVISION")},
              "manual_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "data/manuals").glob("*.md")},
              "human_review_complete": False}
    opener = build_opener(ProxyHandler({}))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = folder / ("m4-quality-" + stamp + ".json")
    for case in cases:
        draft_mode = case["kind"] == "draft"
        token = config["DEMO_OPERATOR_TOKEN" if draft_mode else "DEMO_VIEWER_TOKEN"]
        payload = {"query": case["query"]}
        if draft_mode:
            payload.update(incident_id="INC-014", incident_filters={"from": "2026-08-01T00:00:00+09:00", "to": "2026-09-01T00:00:00+09:00"})
        path = "/v1/ticket-draft-previews" if draft_mode else "/v1/answers"
        request = Request("http://127.0.0.1:8000" + path, data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        started = time.monotonic()
        status, data, error = 0, {}, None
        try:
            with opener.open(request, timeout=65) as response:
                status, data = response.status, json.load(response)
        except HTTPError as exc:
            status = exc.code
            error = "http_error"
        except (URLError, OSError, ValueError) as exc:
            error = transport_error(exc)
        checks = assess(case, status, data)
        row = {**case, "status": status, "error_kind": error, "elapsed_ms": round((time.monotonic()-started)*1000),
               "checks": checks, "contract_passed": all(checks.values()), "human_review": "pending",
               "response": {k: data[k] for k in ("answer", "draft", "citations", "abstain", "source_ids", "mode", "prompt_version", "request_id", "steps") if isinstance(data, dict) and k in data}}
        report["cases"].append(row)
        report["completed"] = len(report["cases"])
        report["contract_passed"] = sum(c["contract_passed"] for c in report["cases"])
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(case["id"], "PASS" if row["contract_passed"] else "FAIL", "HTTP", status, flush=True)
        if status == 0 or status >= 500:
            break
    review = ["# M4 근거 충실도 검토", "", "자동 계약 검사와 의미/근거 검토를 구분합니다. PASS만으로 전체 품질 통과가 아닙니다.", ""]
    for row in report["cases"]:
        review.extend(["## " + row["id"], "", row["query"], "", "검토 기준: " + row["review"], "",
                       "- 판단: 미검토", "- 근거 문장 및 추가/누락 주장:", ""])
    output.with_suffix(".md").write_text("\n".join(review), encoding="utf-8")
    print("결과 저장:", output)
    return 0 if report.get("contract_passed") == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
