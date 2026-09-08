"""검사 이미지 빌드 후 서로 다른 컨테이너에서 PostgreSQL 저장·재개를 확인합니다."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    run_id = str(uuid4())
    compose = ["docker", "compose", "-f", "compose.yaml", "-f", "compose.m3.yaml", "--profile", "tools"]
    report = {"run_id": run_id, "checks": [], "passed": False}
    try:
        for phase, command in [
            ("build", compose + ["build", "checkpoint-check"]),
            ("pause", compose + ["run", "--rm", "checkpoint-check", "pause", run_id]),
            ("resume", compose + ["run", "--rm", "checkpoint-check", "resume", run_id]),
        ]:
            print("검사 단계:", phase, flush=True)
            result = subprocess.run(command, cwd=ROOT, check=False)
            report["checks"].append({"phase": phase, "passed": result.returncode == 0})
            if result.returncode:
                return 1
        report["passed"] = True
        print("PASS: 별도 프로세스 간 PostgreSQL 승인 대기 저장·재개")
        return 0
    finally:
        folder = ROOT / "eval/results"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("m3-checkpoint-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("결과 저장:", path)


if __name__ == "__main__":
    raise SystemExit(main())
