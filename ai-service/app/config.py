import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    business_api_url: str
    business_service_token: str
    viewer_token: str
    operator_token: str

    @classmethod
    def from_env(cls) -> "Settings":
        values = [os.environ.get(key, "") for key in
                  ("BUSINESS_SERVICE_TOKEN", "DEMO_VIEWER_TOKEN", "DEMO_OPERATOR_TOKEN")]
        if any(len(value) < 24 for value in values) or len(set(values)) != 3:
            raise RuntimeError("서로 다른 24자 이상의 서비스·데모 토큰을 설정하세요.")
        url = os.environ.get("BUSINESS_API_URL", "http://business:8080")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise RuntimeError("BUSINESS_API_URL 설정을 확인하세요.")
        return cls(url.rstrip("/"), *values)
