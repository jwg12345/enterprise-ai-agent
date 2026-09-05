# AI Service

M1 FastAPI 조회 프록시를 구현했습니다. 업무 DB를 직접 접근하지 않고 Spring에 인증된 조회만 전달합니다.

- app/config.py: 필수 인증 설정·중복 토큰 검사
- app/models.py: 기간·enum·페이지 및 응답 검증
- app/main.py: 조회 API, 신원 매핑, 요청 ID, 재시도, health
- tests/test_api.py: 인증 위조·입력·upstream 오류·health 검사

루트에서 `uv run pytest ai-service/tests -q`로 검사합니다. 실행은 [통합 실행 안내](../docs/runbook.md)를 따릅니다. LangGraph, RAG, Agent DB 연결과 승인 API는 아직 없습니다.

M2 선택적 코드는 app/rag·app/agent에 추가되었습니다. CPU 의존성 lock·설치와 실제 그래프 검사는 완료했고 모델·통합 검증은 진행 중입니다. [M2 현황](../docs/m2-status.md)을 먼저 확인하세요. 기본 M1 실행에는 선택적 의존성을 import하지 않습니다.

M2 해시 lock은 생성했으며 CPU 의존성 설치 명령은 `uv pip install --python .venv/Scripts/python.exe --torch-backend cpu --require-hashes -r ai-service/requirements-m2.lock`입니다. Linux에서는 `.venv/bin/python`을 사용합니다. 설치 후 `uv run --no-sync pytest ai-service/tests_m2 -q`로 실제 LangGraph 검사를, `uv run --no-sync pytest -q`로 기본 회귀 검사를 실행합니다. `uv run`에 `--no-sync`를 붙여 M1 환경 동기화로 선택적 패키지가 제거되지 않게 합니다. 같은 검사를 CI에 등록했으며 원격 CI 결과는 미확인입니다.
