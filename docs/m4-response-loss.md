# M4 커밋 후 응답 유실 복구 검사

## 범위

실제 Spring/PostgreSQL과 현재 TicketRuntime·LangGraph·PostgreSQL checkpointer를 사용합니다. 검사 전용 HTTP transport가 Spring의 성공 응답을 받은 후 런타임에 전달하지 않고 ReadError를 발생시킵니다. 실제 서버 커밋 이후 클라이언트가 결과를 모르는 상황을 통제해 검사하며 물리 네트워크 차단이나 운영 AI 프로세스 강제 종료 실험과는 구분합니다. FastAPI/UI 응답 경계는 이 검사 대상이 아닙니다.

합성 INC-014에 대해 운영자 소유 승인·티켓 각 1건을 생성합니다. LLM은 호출하지 않습니다. 기존 AI를 재시작하거나 모델을 로딩하지 않으며 오류 주입 코드는 scripts의 검사 도구에만 있습니다.

## 실행

현재 AI 이미지와 실행 중인 Business/PostgreSQL이 필요합니다. 프로젝트 루트의 PowerShell에서:

```powershell
uv run --no-sync python scripts/verify_response_loss.py --execute
```

1. Docker와 실행 중인 Business/PostgreSQL ID를 사전 확인합니다. 실패하면 합성 요청을 시작하지 않습니다.
2. 새 보고서에 요청 키를 먼저 저장하고 일회성 컨테이너에서 실제 승인 대기를 만듭니다.
3. 검사 운영자가 승인합니다. Spring이 티켓을 커밋한 성공 응답은 검사 transport에서 버립니다.
4. 클라이언트가 RECONCILING 오류를 받고 checkpoint에는 execute 노드가 미완료로 남는지 확인합니다. 성공 응답에서 관측한 티켓 ID·원래 멱등 키는 검사 보고서에만 증거로 기록합니다.
5. 첫 프로세스를 종료하고 별도 컨테이너에서 같은 PostgreSQL 실행을 두 번 재개합니다. 원래 키와 티켓 ID가 유지되고 COMPLETED인지 확인합니다.
6. 별도 관리용 psql 연결로 해당 승인에 티켓 1건, 해당 티켓에 TICKET_CREATED 감사 1건인지 집계합니다. AI 서비스 계정의 business 접근 제한은 유지합니다. 검사 집계는 읽기 전용입니다.

출력 파일은 eval/results/m4-response-loss-시간.json입니다. passed=true는 모든 단계 및 DB 집계가 통과했다는 뜻입니다. 단위 테스트 통과와 별개로 실제 결과 파일을 확인해야 합니다.

## 중단 후 재개

실패 시 같은 명령으로 새 검사를 반복하지 말고 결과 파일을 먼저 확인합니다. inject_complete=true이고 passed=false인 보고서는 기존 실행으로만 재개할 수 있습니다.

```powershell
uv run --no-sync python scripts/verify_response_loss.py --execute --resume-report eval/results/실제보고서파일명.json
```

이미 resume_complete=true이면 복구 실행도 반복하지 않고 DB 집계만 재시도합니다. 주입 완료 전 실패는 자동 재개 대상이 아닙니다. 저장된 run_id/request_key로 현재 원장을 먼저 확인해야 하며 새 키나 새 티켓으로 대체하지 않습니다. 기존 보고서와 합성 티켓을 자동 삭제하지 않습니다.

## 현재 검증

검사 transport가 커밋 응답을 한 번만 유실시키는지, 비성공/조회 응답은 보존하는지, 런타임에 RECONCILING으로 전달되는지, 재개 명령이 재주입하지 않는지를 모의 HTTP/명령으로 검증했습니다. 신규 4개 및 기존 실행 API 16개 합계 20 passed, Starlette/AnyIO 경고 1개, Ruff 통과입니다.

앱의 실제 실행 시도는 Docker 사전 확인에서 실패해 합성 요청을 시작하지 않았습니다. 사용자 PowerShell의 실제 통합 실행은 대기입니다.

## 실제 실행 결과 확인 — 2026-09-08

[최종 보고서](../eval/results/m4-response-loss-20260907T114241659635Z.json)를 확인했습니다. inject_complete/resume_complete/passed 모두 true, 원래 멱등 키 유지, 티켓·생성 감사 각각 1건입니다. 위 실제 실행 대기는 과거 기록입니다.
