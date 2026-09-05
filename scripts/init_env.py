"""이미 존재하는 .env는 덮어쓰지 않습니다. 생성한 비밀을 출력하지 않습니다."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
keys = ("POSTGRES_PASSWORD", "BUSINESS_DB_PASSWORD", "AGENT_DB_PASSWORD",
        "BUSINESS_SERVICE_TOKEN", "DEMO_VIEWER_TOKEN", "DEMO_OPERATOR_TOKEN")
target = root / ".env"
with target.open("x", encoding="utf-8") as output:
    output.write("# Local synthetic demo only; do not commit.\n")
    for key in keys:
        output.write(f"{key}={secrets.token_urlsafe(32)}\n")
print("Created .env with local demo credentials (values hidden).")
