"""합성 실행 2건·티켓 1건 생성 및 AI 재시작 후 실제 그래프 복구 검사."""
import argparse
import json
import subprocess
import time
from http.client import HTTPException
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]


def resume_runs(path):
    previous = json.loads(path.read_text(encoding="utf-8"))
    rows = previous["runs"]
    if previous.get("passed") is not False or previous.get("failed_step") not in {"restart AI", "wait for readiness"}:
        raise ValueError("재시작 단계에서 중단된 보고서만 재개할 수 있습니다.")
    if len(rows) != 2 or {r["decision"] for r in rows} != {"approve", "reject"}:
        raise ValueError("승인/거절 실행 2건이 필요합니다.")
    for row in rows:
        UUID(row["run_id"])
        UUID(row["approval_id"])
    return rows


def wait_ready(call, timeout=300):
    deadline = time.monotonic() + timeout
    while True:
        try:
            status, ready = call("GET", "/health/ready")
            if status == 200 and ready.get("stage") == "M3":
                return
        except (URLError, OSError, HTTPException, ValueError):
            # 재시작 직후 reset/불완전 HTTP/JSON 응답은 준비 대기 중에만 재시도합니다.
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError("readiness timeout")
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true", help="AI 재시작과 합성 티켓 생성 허용")
    parser.add_argument("--resume-report", type=Path, help="재시작 단계에서 실패한 보고서의 기존 실행 재사용")
    parser.add_argument("--after-restart", action="store_true", help="보고서에 성공 기록이 있는 재시작을 반복하지 않음")
    args = parser.parse_args()
    if not args.restart:
        parser.error("--restart를 지정하세요. AI를 재시작하고 합성 데이터를 생성합니다.")
    try:
        existing = resume_runs(args.resume_report) if args.resume_report else []
        if args.after_restart:
            prior = json.loads(args.resume_report.read_text(encoding="utf-8")) if args.resume_report else {}
            if not any(c.get("name") == "restart AI" and c.get("passed") is True for c in prior.get("checks", [])):
                raise ValueError("성공한 재시작 기록이 필요합니다.")
    except (OSError, ValueError, KeyError, TypeError):
        parser.error("재개 보고서 형식이나 중단 단계를 확인하세요.")
    config = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip().strip("\"'")
    token = config["DEMO_OPERATOR_TOKEN"]
    report = {"checks": [], "runs": existing, "passed": False}
    if args.resume_report:
        report["resumed_from"] = args.resume_report.name
    phase = "start"

    def call(method, path, data=None, key=None, viewer=False):
        headers = {"Authorization": "Bearer " + (config["DEMO_VIEWER_TOKEN"] if viewer else token),
                   "Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        req = Request("http://127.0.0.1:8000" + path, method=method, headers=headers,
                      data=json.dumps(data).encode() if data is not None else None)
        try:
            with build_opener(ProxyHandler({})).open(req, timeout=55) as res:
                return res.status, json.load(res)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError(name)
        print("PASS:", name, flush=True)

    try:
        for decision in (() if existing else ("reject", "approve")):
            phase = decision + " register"
            key = str(uuid4())
            draft = {"draft": {"incident_id": "INC-014", "title": "[M3 graph smoke] 합성 점검",
                               "body": "영속 실행 통합 검사", "team": "Platform", "priority": "P1"}}
            status, run = call("POST", "/v1/ticket-runs", draft, key)
            check(phase, status == 200 and run.get("status") == "WAITING_APPROVAL" and not run.get("ticket_id"))
            report["runs"].append({"decision": decision, "run_id": run["run_id"], "approval_id": run["approval"]["approval_id"], "key": key})
            status, repeated = call("POST", "/v1/ticket-runs", draft, key)
            check(decision + " duplicate start", status == 200 and repeated.get("run_id") == run["run_id"])
            changed = {"draft": {**draft["draft"], "title": "변경"}}
            status, _ = call("POST", "/v1/ticket-runs", changed, key)
            check(decision + " changed key payload blocked", status == 409)
            status, _ = call("GET", "/v1/ticket-runs/" + run["run_id"], viewer=True)
            check(decision + " viewer blocked", status == 403)
        phase = "restart AI"
        if not args.after_restart:
            result = subprocess.run(["docker", "compose", "-f", "compose.yaml", "-f", "compose.m2.yaml",
                                 "-f", "compose.m3-app.yaml", "--profile", "rag", "restart", "ai"], cwd=ROOT, check=False)
            check(phase, result.returncode == 0)
        else:
            report["restart_reused"] = True
        phase = "wait for readiness"
        wait_ready(call)
        check(phase, True)
        for row in report["runs"]:
            path = "/v1/ticket-runs/" + row["run_id"]
            phase = row["decision"] + " restore"
            status, run = call("GET", path)
            check(phase, status == 200 and run.get("status") == "WAITING_APPROVAL")
            payload = {"approval_id": row["approval_id"], "decision": row["decision"]}
            phase = row["decision"] + " decide"
            status, run = call("POST", path + "/decisions", payload)
            expected = "REJECTED" if row["decision"] == "reject" else "COMPLETED"
            check(phase, status == 200 and run.get("status") == expected)
            row["ticket_id"] = run.get("ticket_id")
            check(phase + " ticket", bool(run.get("ticket_id")) == (expected == "COMPLETED"))
            if expected == "COMPLETED":
                phase = "concurrent duplicate decisions"
                with ThreadPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(lambda _: call("POST", path + "/decisions", payload), range(4)))
                check(phase, all((s == 200 and b.get("ticket_id") == row["ticket_id"]) or
                                 (s == 409 and b.get("error", {}).get("code") == "RUN_BUSY") for s, b in results))
        report["passed"] = True
    except (RuntimeError, KeyError, ValueError, URLError, TimeoutError, OSError, HTTPException) as exc:
        report["failed_step"] = phase
        report["error_type"] = type(exc).__name__
        print("FAIL:", phase, "— 저장된 실행을 확인하세요. 자동 재생성하지 않습니다.")
    finally:
        folder = ROOT / "eval/results"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("m3-ticket-runs-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("결과 저장:", path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
