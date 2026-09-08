"""합성 승인·티켓 1건으로 응답 유실→별도 프로세스 재개→DB 중복/감사 개수를 검증합니다."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", "compose.yaml", "-f", "compose.m2.yaml", "-f", "compose.m3-app.yaml",
           "-f", "compose.m4-check.yaml", "--profile", "rag", "--profile", "tools"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="합성 승인·티켓 1건 생성 허용. LLM 호출 없음")
    parser.add_argument("--resume-report", type=Path, help="주입 완료한 기존 결과의 복구·DB 검증만 재개")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute가 필요합니다.")
    preflight = subprocess.run(COMPOSE + ["ps", "-q", "business", "postgres"], cwd=ROOT, capture_output=True, text=True)
    if preflight.returncode or len(preflight.stdout.split()) != 2:
        raise SystemExit("Docker/Business/PostgreSQL 확인 실패. 합성 요청을 시작하지 않았습니다.")
    folder = ROOT / "eval/results"
    folder.mkdir(parents=True, exist_ok=True)
    if args.resume_report:
        path = args.resume_report.resolve()
        if path.parent != folder.resolve():
            parser.error("eval/results의 보고서만 재개할 수 있습니다.")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not report.get("inject_complete") or report.get("passed"):
            parser.error("주입 완료·최종 미통과 보고서만 재개하세요.")
        phases = ("resume",) if not report.get("resume_complete") else ()
    else:
        path = folder / ("m4-response-loss-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        report = {"request_key": str(uuid4()), "passed": False,
                  "scope": "real Spring/PostgreSQL; test transport drops committed response; separate recovery process"}
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        phases = ("inject", "resume")
    try:
        for phase in phases:
            result = subprocess.run(COMPOSE + ["run", "--rm", "--no-deps", "response-loss-check", phase, path.name],
                                    cwd=ROOT, check=False)
            if result.returncode:
                return 1
        report = json.loads(path.read_text(encoding="utf-8"))
        approval, ticket = str(UUID(report["approval_id"])), str(UUID(report["committed_ticket_id"]))
        # 별도 운영 검증 계정의 읽기 전용 집계. AI 서비스는 business 스키마에 접근하지 않습니다.
        sql = ("SELECT json_build_object('tickets',(SELECT count(*) FROM business.tickets WHERE approval_id='" + approval +
               "'::uuid),'ticket_audits',(SELECT count(*) FROM business.audit_events WHERE action='TICKET_CREATED' AND resource_id='" + ticket + "'::uuid));")
        result = subprocess.run(COMPOSE + ["exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "enterprise",
                                          "-v", "ON_ERROR_STOP=1", "-Atc", sql], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            report["failed_phase"] = "database_counts"
        else:
            report["database_counts"] = json.loads(result.stdout)
            report["passed"] = report["database_counts"] == {"tickets": 1, "ticket_audits": 1}
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS" if report["passed"] else "FAIL", ": 티켓·생성 감사 각각 1건")
        return 0 if report["passed"] else 1
    finally:
        print("결과 저장:", path)


if __name__ == "__main__":
    raise SystemExit(main())
