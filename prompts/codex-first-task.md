# Codex 첫 작업 프롬프트

아래 구분선 이후 내용을 이 저장소를 연 개발 작업의 첫 요청으로 사용합니다.

---

이 저장소의 `기업 업무 대응 AI Agent` 구현을 시작해 주세요. 먼저 README.md, docs/architecture.md, docs/operations.md, AGENTS.md, docs/api-contract.md를 읽고 기존 파일을 확인하세요. 한글로 진행 상황과 결과를 설명하세요.

이번 작업은 **M1: 로컬 실행 가능한 서비스 스캐폴딩과 장애 조회**까지입니다. 모든 M2~M4 기능을 한 번에 구현하지 마세요.

1. 설치된 Python·Java·Docker 환경을 확인하고 호환 의존성 버전을 공식 문서로 검증해 고정하세요. Python은 FastAPI와 pytest, Java는 Spring Boot와 JUnit, UI는 Streamlit으로 구성하세요. 재현 가능한 lockfile과 Java build wrapper를 준비하세요.
2. FastAPI의 `/health/live`, `/health/ready`, Spring의 Actuator health 및 `/api/v1/incidents`를 구현하세요. query validation, 공통 오류 모델, request_id 전파, 서버 측 로컬 데모 신원 검증을 포함하세요.
3. PostgreSQL business/agent 스키마와 분리 계정을 구성하고 Flyway로 incidents 테이블을 만드세요. data/fixtures/incidents.json의 합성 데이터를 명시적 seed 작업으로 적재하세요. 일반 기동마다 데이터를 초기화하지 마세요.
4. Streamlit에서 기간·등급·분류로 조회하고 FastAPI가 Spring을 통해 반환한 장애 표를 표시하세요. M1 조회용 FastAPI `GET /v1/incidents` 프록시 계약을 API 문서에 추가하세요. 아직 구현하지 않은 채팅·RAG·승인 버튼을 실제 기능처럼 보이게 하지 마세요.
5. 루트 compose.yaml과 각 서비스 Dockerfile을 만들고 README에서 참조하세요. PostgreSQL·Chroma·Business·AI·UI를 구성하되 아직 없는 인덱스를 준비 완료로 표시하지 마세요. M1의 readiness 범위는 단계별로 명시하세요. UI와 필요 개발 API만 loopback에 노출하고 DB는 내부 네트워크에 두세요. `.env.example`을 작성하세요.
6. pytest로 입력 검증·인증·API 실패 처리를, JUnit으로 조회 필터·페이지 제한을 검증하세요. 실제 PostgreSQL migration·seed·조회 통합 검증을 수행하고 GitHub Actions에 필요한 검사 작업을 추가하세요. 대체 저장소로 실행한 테스트를 PostgreSQL 검증이라고 보고하지 마세요.
7. 새 환경의 실행/종료 명령, 모델 다운로드가 M1에서 필요한지 여부, 실제 검증 결과를 문서에 남기세요. 실행할 수 없는 도구가 있다면 가능한 검사를 수행하고 미검증 범위를 정확히 보고하세요.

완료 기준: Compose로 서비스 기동, readiness의 단계별 조건 확인, 합성 장애 필터 조회, Streamlit 표 표시, 키 없는 테스트 및 CI 구성, 재현 가능한 실행 문서. 아직 실제 RAG와 영속 승인·티켓 생성은 구현하지 않았음을 README에 유지하세요. 비밀을 저장하지 말고 사용자의 기존 변경은 보존하세요.
