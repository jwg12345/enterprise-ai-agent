# AI Service

M4 기동 워밍업: Compose의 RAG_WARMUP=true에서는 합성 문구로 CPU 임베딩·검색을 1회 수행한 뒤 startup을 완료합니다(최대 120초, 실패 시 기동 실패). LLM 호출은 없으며 코드 기본값은 false입니다. 초기 임베딩 지연 완화 목적이고 장시간 idle 이후 성능 보장은 아닙니다. 관련 검사는 `uv run --no-sync pytest ai-service/tests/test_startup_warmup.py ai-service/tests/test_rag_contracts.py -q`입니다. 실제 적용·성능 결과는 [M4 현황](../docs/m4-status.md)을 우선 확인하세요.

자연어 초안 미리보기: app/draft_previews.py 및 app/agent/draft_preview.py. `/v1/ticket-draft-previews`는 조회·검색·LLM 초안 생성만 하며 승인·티켓 쓰기와 분리합니다. `test_draft_preview.py` 19개 통과, 실제 제공자 검증은 대기입니다. 장애 ID/등급은 실제 조회에서, 팀은 합성 분류 정책에서 결정합니다. 기존 LLM_MODE=compatible 설정을 사용합니다.

최신 M3 검사 결과: 사용자 PowerShell에서 기존 조회+신규 승인 API 32개 통과, 경고 1개(Starlette/AnyIO 폐기 예정 별칭). 아래 앱 실행 제약 이후 확보한 결과입니다. 실제 Spring/컨테이너 연동은 아직 검증 전입니다.

M3 중간 연결 코드: `app/approvals.py`에서 승인·티켓 Spring API를 프록시합니다. 인증된 operator만 쓰기가 가능하며 UI/LangGraph 자동 실행과 영속 runs는 아직 없습니다. 신규 `tests/test_approvals.py` 16개는 정적 검사 통과·실행 검증 대기입니다. `uv run --no-sync pytest ai-service/tests/test_api.py ai-service/tests/test_approvals.py -q`로 기존 조회와 함께 검사합니다. 앱에서는 orjson DLL 접근 거부가 발생했으며 사용자 PowerShell 검증이 필요합니다. [M3 현황](../docs/m3-status.md)의 명령과 구현 범위를 참고하세요.

정책 질문 과차단 회귀 검사는 `uv run --no-sync pytest ai-service/tests/test_guardrails.py -q`입니다. 정책 설명·생성 지시·혼합 요청·금지 입력 우선순위와 실제 Agent route 연결을 검사합니다. 기존 전체 pytest/CI 수집에 포함됩니다. 전체 실행 시 Windows 임시 폴더 접근 문제가 있으면 [최신 M2 절차](../docs/m2-status.md)의 고유 --basetemp 명령을 사용합니다. 컨테이너 적용 후 실제 API 재검증이 필요합니다.

M1 FastAPI 조회 프록시를 구현했습니다. 업무 DB를 직접 접근하지 않고 Spring에 인증된 조회만 전달합니다.

- app/config.py: 필수 인증 설정·중복 토큰 검사
- app/models.py: 기간·enum·페이지 및 응답 검증
- app/main.py: 조회 API, 신원 매핑, 요청 ID, 재시도, health
- tests/test_api.py: 인증 위조·입력·upstream 오류·health 검사

루트에서 `uv run pytest ai-service/tests -q`로 검사합니다. 실행은 [통합 실행 안내](../docs/runbook.md)를 따릅니다. LangGraph, RAG, Agent DB 연결과 승인 API는 아직 없습니다.

M2 선택적 코드는 app/rag·app/agent에 추가되었습니다. CPU 의존성 lock·설치와 실제 그래프 검사는 완료했고 모델·통합 검증은 진행 중입니다. [M2 현황](../docs/m2-status.md)을 먼저 확인하세요. 기본 M1 실행에는 선택적 의존성을 import하지 않습니다.

M2 해시 lock은 생성했으며 CPU 의존성 설치 명령은 `uv pip install --python .venv/Scripts/python.exe --torch-backend cpu --require-hashes -r ai-service/requirements-m2.lock`입니다. Linux에서는 `.venv/bin/python`을 사용합니다. 설치 후 `uv run --no-sync pytest ai-service/tests_m2 -q`로 실제 LangGraph 검사를, `uv run --no-sync pytest -q`로 기본 회귀 검사를 실행합니다. `uv run`에 `--no-sync`를 붙여 M1 환경 동기화로 선택적 패키지가 제거되지 않게 합니다. 같은 검사를 CI에 등록했으며 원격 CI 결과는 미확인입니다.
