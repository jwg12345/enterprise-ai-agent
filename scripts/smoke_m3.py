"""로컬 합성 장애에 승인 2건·티켓 1건을 남기는 실제 M3 연결 검사."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="합성 승인 2건·티켓 1건 생성")
    args = parser.parse_args()
    if not args.execute:
        parser.error("실제 합성 데이터를 생성하는 검사입니다. --execute를 지정하세요.")
    config = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip().strip("\"'")
    operator = os.environ.get("DEMO_OPERATOR_TOKEN", config.get("DEMO_OPERATOR_TOKEN", ""))
    viewer = os.environ.get("DEMO_VIEWER_TOKEN", config.get("DEMO_VIEWER_TOKEN", ""))
    if min(len(operator), len(viewer)) < 24:
        raise SystemExit("조회자·운영자 토큰 설정이 필요합니다.")
    # 비밀 전송 대상을 로컬 데모로 고정합니다.
    base = "http://127.0.0.1:8000"
    opener = build_opener(ProxyHandler({}))
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": [], "resources": {}}
    current = "readiness"

    def call(method, path, token=operator, payload=None, key=None):
        headers = {"Authorization": "Bearer " + token, "X-Request-ID": str(uuid4())}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if key:
            headers["Idempotency-Key"] = key
        req = Request(base + path, headers=headers, method=method,
                      data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with opener.open(req, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            try:
                body = json.load(exc)
            except ValueError:
                body = {}
            return exc.code, body

    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError(name)
        print("PASS:", name)

    try:
        status, _ = call("GET", "/health/ready")
        check(current, status == 200)
        current = "synthetic incident available"
        params = urlencode({"from": "2026-08-01T00:00:00+09:00", "to": "2026-09-01T00:00:00+09:00",
                            "status": "OPEN", "size": 50})
        status, page = call("GET", "/v1/incidents?" + params)
        rows = page.get("items", [])
        check(current, status == 200 and any(r["id"] == "INC-014" for r in rows))
        draft = {"incident_id": "INC-014", "title": "[M3 smoke] 합성 후속 점검",
                 "body": "연동 검사에서 생성한 합성 티켓입니다. 실제 시스템 변경을 지시하지 않습니다.",
                 "team": "Platform", "priority": "P1"}
        for decision in ("reject", "approve"):
            current = decision + " proposal"
            run_id = str(uuid4())
            report["resources"][decision + "_run_id"] = run_id
            proposal = {"run_id": run_id, "proposal_version": 1, "draft": draft}
            status, approval = call("POST", "/v1/approvals", payload=proposal)
            check(current, status == 201 and approval.get("status") == "PENDING")
            approval_id = approval["approval_id"]
            report["resources"][decision + "_approval_id"] = approval_id
            path = "/v1/approvals/" + approval_id
            payload = {"approval_id": approval_id, "draft_hash": approval["draft_hash"]}
            key = "m3-smoke-" + run_id
            report["resources"][decision + "_idempotency_key"] = key
            current = decision + " pending write blocked"
            status, body = call("POST", "/v1/tickets", payload=payload, key=key)
            check(current, status == 409 and body.get("error", {}).get("code") == "APPROVAL_REQUIRED")
            current = decision + " viewer decision blocked"
            status, _ = call("POST", path + "/decision", token=viewer, payload={"decision": "approve"})
            check(current, status == 403)
            current = decision + " decision recorded"
            status, body = call("POST", path + "/decision", payload={"decision": decision})
            check(current, status == 200 and body.get("status") == ("REJECTED" if decision == "reject" else "APPROVED"))
            current = decision + " ticket result"
            status, body = call("POST", "/v1/tickets", payload=payload, key=key)
            if decision == "reject":
                check(current, status == 409 and body.get("error", {}).get("code") == "APPROVAL_REQUIRED")
                continue
            check(current, status == 201 and bool(body.get("id")))
            ticket_id = body["id"]
            report["resources"]["ticket_id"] = ticket_id
            current = "same key returns same ticket"
            status, body = call("POST", "/v1/tickets", payload=payload, key=key)
            check(current, status == 200 and body.get("id") == ticket_id)
            current = "executed ledger points to ticket"
            status, body = call("GET", path)
            check(current, status == 200 and body.get("status") == "EXECUTED" and body.get("ticket_id") == ticket_id)
            current = "ticket read"
            status, body = call("GET", "/v1/tickets/" + ticket_id)
            check(current, status == 200 and body.get("id") == ticket_id)
        report["passed"] = True
    except (RuntimeError, KeyError, ValueError, URLError, TimeoutError):
        report["passed"] = False
        report["failed_step"] = current
        print("FAIL:", current, "— 상태를 확인하세요. 자동 재생성하지 않습니다.")
    finally:
        folder = ROOT / "eval/results"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("m3-smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("결과 저장:", path)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
