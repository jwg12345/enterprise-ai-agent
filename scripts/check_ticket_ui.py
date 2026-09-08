"""실제 API를 사용하는 거절 화면 AppTest. 합성 승인 1건을 남기며 티켓은 만들지 않습니다."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    from streamlit.testing.v1 import AppTest
    config = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip().strip("\"'")
    os.environ.update(M3_ENABLED="true", M2_ENABLED="false", AI_API_URL="http://127.0.0.1:8000",
                      DEMO_OPERATOR_TOKEN=config["DEMO_OPERATOR_TOKEN"])
    sys.path.insert(0, str(ROOT / "demo-ui"))
    from tickets_ui import ticket_request
    report = {"passed": False, "checks": []}
    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError(name)
        print("PASS:", name)
    try:
        app = AppTest.from_file(str(ROOT / "demo-ui/app.py"), default_timeout=60).run()
        next(t for t in app.text_input if t.label == "티켓 제목").set_value("[UI reject check] 합성 거절 검증")
        next(b for b in app.button if b.label == "초안 등록 · 승인 대기").click().run()
        check("real pending UI", not app.exception and not app.error and any(b.label == "거절" for b in app.button))
        run = app.session_state["ticket_run"]
        report["run_id"] = run["run_id"]
        report["approval_id"] = run["approval"]["approval_id"]
        next(b for b in app.button if b.label == "거절").click().run()
        check("real rejected UI", not app.exception and any("거절됨" in item.value for item in app.markdown))
        check("no approve action", not any(b.label == "승인하고 티켓 생성" for b in app.button))
        result = ticket_request("GET", "/v1/ticket-runs/" + run["run_id"])
        check("real ledger rejected without ticket", result["status"] == "REJECTED" and not result["ticket_id"])
        report["passed"] = True
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        print("FAIL: 실제 거절 화면 검사를 완료하지 못했습니다.")
    finally:
        folder = ROOT / "eval/results"
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / ("m3-ui-reject-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("결과 저장:", output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
