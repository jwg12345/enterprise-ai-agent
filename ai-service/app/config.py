#서버 설정 및 토큰 관리
import os
from dataclasses import dataclass
from urllib.parse import urlparse

#서버가 동작하는 데 필요한 설정값을 관리하는 클래스
@dataclass(frozen=True)
class Settings: 
    business_api_url: str
    business_service_token: str
    viewer_token: str
    operator_token: str

    #운영체제 환경변수에서 세가지 토큰을 읽어옴
    # BUSINESS_SERVICE_TOKEN	FastAPI가 Spring Boot에 요청할 때 사용하는 서비스 인증 토큰
    # DEMO_VIEWER_TOKEN	조회 권한 사용자 인증
    # DEMO_OPERATOR_TOKEN	승인·티켓 실행 권한 사용자 인증
    @classmethod
    def from_env(cls) -> "Settings":
        values = [os.environ.get(key, "") for key in
                  ("BUSINESS_SERVICE_TOKEN", "DEMO_VIEWER_TOKEN", "DEMO_OPERATOR_TOKEN")]
        #검증 수행 1.모든 토큰이 최소 24자여야 한다는 것 2.세 토큰이 서로 달라야 한다는 것
        #len(set(values)) != 3은 중복 제거 후 토큰 개수가 3개가 아니면 중복이 존재한다는 의미
        if any(len(value) < 24 for value in values) or len(set(values)) != 3:
            raise RuntimeError("서로 다른 24자 이상의 서비스·데모 토큰을 설정하세요.")
        #Spring Boot 서버의 주소를 가져옴
        url = os.environ.get("BUSINESS_API_URL", "http://business:8080")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise RuntimeError("BUSINESS_API_URL 설정을 확인하세요.")
        return cls(url.rstrip("/"), *values)
