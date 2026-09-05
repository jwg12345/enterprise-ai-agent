import os
import uuid

import httpx


class QueryError(Exception):
    pass


def fetch_incidents(params: dict) -> tuple[dict, str]:
    token = os.environ.get("DEMO_VIEWER_TOKEN", "")
    if len(token) < 24:
        raise QueryError("서버의 조회자 인증 설정이 필요합니다.")
    request_id = str(uuid.uuid4())
    try:
        response = httpx.get(
            os.environ.get("AI_API_URL", "http://ai:8000") + "/v1/incidents",
            params=params, headers={"Authorization": "Bearer " + token, "X-Request-ID": request_id},
            timeout=20, trust_env=False
        )
        if response.status_code != 200:
            raise QueryError(f"조회를 완료하지 못했습니다. 요청 ID: {request_id}")
        return response.json(), request_id
    except (httpx.HTTPError, ValueError):
        raise QueryError(f"조회 서비스에 연결할 수 없습니다. 요청 ID: {request_id}") from None
