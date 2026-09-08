"""읽기 전용 M4 진단. LLM 호출·재시작·환경 변수/원문 로그 수집을 하지 않습니다."""
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]


def docker(args):
    try:
        result = subprocess.run(["docker", *args], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main():
    report = {"read_only": True, "health": {}, "containers": []}
    opener = build_opener(ProxyHandler({}))
    for endpoint in ("live", "ready"):
        started = time.monotonic()
        try:
            with opener.open("http://127.0.0.1:8000/health/" + endpoint, timeout=8) as response:
                data = json.load(response)
                report["health"][endpoint] = {"http_status": response.status,
                    "state": {k: data.get(k) for k in ("status", "stage", "agent_db", "business", "rag")}}
        except Exception as exc:
            report["health"][endpoint] = {"error_type": type(exc).__name__}
        report["health"][endpoint]["elapsed_ms"] = round((time.monotonic()-started)*1000)
    compose = ["compose", "-f", "compose.yaml", "-f", "compose.m2.yaml", "-f", "compose.m3-app.yaml", "--profile", "rag"]
    raw_ids = docker([*compose, "ps", "-q"])
    report["docker_access"] = "available" if raw_ids is not None else "failed"
    ids = [s for s in (raw_ids or "").splitlines() if re.fullmatch(r"[0-9a-f]{12,64}", s)]
    for cid in ids:
        row = {"id": cid[:12]}
        state = docker(["inspect", "--format", "{{json .State}}", cid])
        if state:
            try:
                data = json.loads(state)
                row["state"] = {k: data.get(k) for k in ("Status", "OOMKilled", "ExitCode", "StartedAt")}
            except ValueError:
                row["state_error"] = "invalid_json"
        stats = docker(["stats", "--no-stream", "--format", "{{json .}}", cid])
        if stats:
            try:
                data = json.loads(stats)
                row["stats"] = {k: data.get(k) for k in ("Name", "CPUPerc", "MemUsage", "MemPerc", "PIDs")}
            except ValueError:
                row["stats_error"] = "invalid_json"
        report["containers"].append(row)
    folder = ROOT / "eval/results"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("m4-runtime-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("결과 저장:", path)
    return 0 if report["docker_access"] == "available" and ids else 1


if __name__ == "__main__":
    raise SystemExit(main())
