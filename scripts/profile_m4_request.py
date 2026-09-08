"""합성 질문 1건과 AI 컨테이너 자원을 함께 측정합니다. 재시작·티켓 생성은 없습니다."""
import argparse
import json
import re
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from diagnose_m4_runtime import ROOT, docker
from evaluate_m4 import transport_error


def numeric_fields(text, keys):
    result = {}
    for line in (text or "").splitlines():
        key, _, value = line.partition(":")
        if key in keys and re.fullmatch(r"\s*\d+(?:\s+kB)?\s*", value):
            result[key] = value.strip()
    return result


def sample(cid):
    row = {"process": numeric_fields(docker(["exec", cid, "cat", "/proc/1/status"]),
                                    {"VmRSS", "VmHWM", "VmSwap", "Threads"}),
           "vm": numeric_fields(docker(["exec", cid, "cat", "/proc/meminfo"]),
                               {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"})}
    raw = docker(["stats", "--no-stream", "--format", "{{json .}}", cid])
    if raw:
        try:
            data = json.loads(raw)
            row["stats"] = {k: data.get(k) for k in ("CPUPerc", "MemUsage", "MemPerc", "PIDs")}
        except ValueError:
            row["stats_error"] = "invalid_json"
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="실제 API 질문 1회, LLM 비용이 발생할 수 있음")
    if not parser.parse_args().execute:
        parser.error("--execute가 필요합니다.")
    ids = docker(["compose", "-f", "compose.yaml", "-f", "compose.m2.yaml", "-f", "compose.m3-app.yaml",
                  "--profile", "rag", "ps", "-q", "ai"])
    cid = (ids or "").strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", cid):
        raise SystemExit("Docker AI 컨테이너 조회 실패. API를 호출하지 않았습니다.")
    config = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip().strip("\"'")
    query = "장애 상태 IN_PROGRESS와 RESOLVED의 의미는 어떻게 다른가요?"
    request = Request("http://127.0.0.1:8000/v1/answers", data=json.dumps({"query": query}).encode(),
                      headers={"Authorization": "Bearer " + config["DEMO_VIEWER_TOKEN"], "Content-Type": "application/json"})
    report = {"question_count": 1, "query": query, "baseline": sample(cid), "samples": [], "response": {}}
    done = threading.Event()
    started = time.monotonic()
    def ask():
        result = {}
        try:
            try:
                response = build_opener(ProxyHandler({})).open(request, timeout=65)
            except HTTPError as exc:
                response = exc
            with response:
                result["http_status"] = response.status
                data = json.load(response)
                code = data.get("error", {}).get("code")
                if code in {"ANSWER_TIMEOUT", "ANSWER_FAILED", "RAG_UNAVAILABLE", "RAG_NOT_ENABLED"}:
                    result["error_code"] = code
                rid = data.get("request_id", "")
                if isinstance(rid, str) and re.fullmatch(r"[a-f0-9-]{36}", rid):
                    result["request_id"] = rid
                result["retrieval_ms"] = [s["duration_ms"] for s in data.get("steps", [])
                    if isinstance(s, dict) and s.get("node") == "retrieve_manual" and isinstance(s.get("duration_ms"), (int, float))]
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            result["error_kind"] = transport_error(exc)
        finally:
            result["elapsed_ms"] = round((time.monotonic()-started)*1000)
            report["response"] = result
            done.set()
    threading.Thread(target=ask, daemon=True).start()
    for _ in range(10):
        if done.wait(2):
            break
        row = sample(cid)
        row["elapsed_ms"] = round((time.monotonic()-started)*1000)
        report["samples"].append(row)
        print("자원 측정:", row["elapsed_ms"], "ms", flush=True)
        if time.monotonic()-started > 70:
            break
    done.wait(min(60, max(0, 70-(time.monotonic()-started))))
    report["request_finished"] = done.is_set()
    report["after"] = sample(cid)
    folder = ROOT / "eval/results"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("m4-request-profile-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("응답:", json.dumps(report["response"], ensure_ascii=False))
    print("결과 저장:", path)
    return 0 if report["response"].get("http_status") == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
