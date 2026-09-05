"""기동·seed 후 실행. 실제 AI → Spring → PostgreSQL 경로를 검사합니다."""
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

root = Path(__file__).resolve().parents[1]
config = {}
if (root / ".env").exists():
    config = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines()
                  if line and not line.startswith("#"))
token = os.environ.get("DEMO_VIEWER_TOKEN", config.get("DEMO_VIEWER_TOKEN", ""))
base = os.environ.get("AI_API_URL", "http://127.0.0.1:8000")
params = {"from": "2026-08-01T00:00:00+09:00", "to": "2026-09-01T00:00:00+09:00",
          "severity": "P1", "category": "NETWORK"}


def query(values, authenticated=True):
    headers = {"Authorization": "Bearer " + token} if authenticated else {}
    request = urllib.request.Request(base + "/v1/incidents?" + urllib.parse.urlencode(values),
                                     headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


with urllib.request.urlopen(base + "/health/ready") as response:
    ready = json.load(response)
    assert ready["stage"] == "M1" and ready["rag"] == "NOT_IMPLEMENTED"
status, data = query(params)
assert status == 200, data
assert {row["id"] for row in data["items"]} == {"INC-014", "INC-015"}, data
assert data["total"] == 2
assert query({**params, "size": 51})[0] == 422
assert query(params, authenticated=False)[0] == 401
assert query({**params, "status": "OPEN"})[1]["total"] == 1
assert query({**params, "page": 1, "size": 1})[1]["items"][0]["id"] == "INC-014"
with urllib.request.urlopen("http://127.0.0.1:8501/_stcore/health") as response:
    assert response.status == 200
print("PASS: readiness, real incidents, filters, pagination, validation, authentication, UI health")
