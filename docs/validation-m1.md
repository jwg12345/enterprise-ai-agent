# M1 검증 결과

검증일: 2026-09-05. 로컬 환경에서 실행한 결과이며 GitHub Actions 원격 실행 결과는 아닙니다.

## 확인한 동작

Streamlit → FastAPI → Spring Boot → PostgreSQL 조회 경로가 동작합니다. 브라우저에서 기본 조건(2026년 8월, P1, NETWORK)으로 조회해 INC-015(RESOLVED)와 INC-014(OPEN) 두 행을 확인했습니다. 발생 시각은 Asia/Seoul로 표시됩니다.

## 실행 환경

- 호스트: Windows, Java 21.0.4, Python 3.12.14, uv 0.10.11
- Docker Engine 29.2.1, Compose v5.1.0, Linux containers
- Spring Boot 3.5.16, Maven 3.9.11, Maven Wrapper 3.3.4
- PostgreSQL 17.6
- FastAPI 0.141.1, Streamlit 1.63.0, Pydantic 2.13.5
- Python 전체 의존성: [uv.lock](../uv.lock)
- 컨테이너 Python: 3.12.12, Java: Temurin 21
- Chroma 1.5.5: 선택적 프로필 기동·heartbeat만 확인

JRE 컨테이너는 Java 21 계열 태그를 사용하므로 패치 이미지가 갱신될 수 있습니다. 엄격한 이미지 재현성은 향후 검증 digest 고정으로 보강할 수 있습니다.

## 결과

| 검사 | 실행/방법 | 결과 |
|---|---|---|
| Python API·화면 | uv run pytest -q | 17건 통과 |
| Python 정적 검사 | uv run ruff check ai-service demo-ui scripts | 통과 |
| Java 단위/API | Maven test (verify 과정 포함) | 15건 통과 |
| 실제 PostgreSQL 통합 | Maven verify -Pintegration | 1건 통과, skip 0 |
| 컨테이너 빌드·기동 | docker compose up --build -d --wait | DB·Business·AI·UI healthy |
| 합성 데이터 최초 적재 | docker compose run --rm seed | 4건 삽입 |
| 합성 데이터 재적재 | 동일 seed 작업 재실행 | 0건 추가, 기존 데이터 보존 |
| 전체 조회 smoke | python scripts/smoke.py | 기간·enum·페이지·401/422·UI health 통과 |
| 스키마 권한 분리 | PostgreSQL privilege 조회 | Agent→업무 읽기 거절, Business→Agent 접근 거절 |
| 구조화 로그 | 실제 AI/Business 로그 대조 | 같은 request_id 확인 |
| 비밀 로그 검사 | .env의 실제 비밀 문자열과 로그 대조 | 설정 비밀 문자열 검출 0건 |
| 브라우저 확인 | 실제 장애 조회 버튼 클릭 | 2건 표시·각 장애 ID/상태/발생 시각 확인 |
| Chroma 기동 | rag 프로필 및 /api/v2/heartbeat | HTTP 200; 확인 후 정지 |

비밀 검사 결과는 이번 실행의 설정 문자열에 대한 검사이며 모든 유형의 개인정보 비노출을 증명하지는 않습니다.

## 남은 범위

- 실제 LLM·LangGraph·BGE-M3·문서 인덱스·영속 HITL·티켓 생성은 아직 없습니다.
- 모델 성능, 검색 품질, p95 지연, 부하 테스트 수치는 아직 측정하지 않았습니다.
- pytest는 외부 의존성 deprecation 경고 2개와 함께 통과했습니다. [TS-007](troubleshooting.md#ts-007--테스트-의존성의-사용-중단-예정-경고)에 추적 내용을 기록했습니다.
- GitHub 저장소 업로드와 원격 CI 실행은 하지 않았습니다.

## 재실행

[실행 안내](runbook.md)를 따릅니다. 테스트 모드의 응답 대체와 실제 PostgreSQL/Compose 검증을 구분합니다. Maven 통합 검증은 별도 임시 DB를 사용하므로 실행 중인 데모 DB를 변경하지 않습니다.

## 버전 확인 참고

- [Spring Boot 3.5 시스템 요구사항](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [FastAPI 공식 배포 정보](https://pypi.org/project/fastapi/0.141.1/)
- [Streamlit 공식 배포 정보](https://pypi.org/project/streamlit/1.63.0/)
- [Maven Wrapper 공식 안내](https://maven.apache.org/wrapper/)
