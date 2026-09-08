> 2026-09-08: 이 문서는 과거 개발 기록입니다. 현재 범위와 다음 작업은 [최종 정리](final-status.md)와 [남은 작업](remaining-work.md)을 우선합니다. 추가 성능 검사는 진행하지 않습니다.

# M3 구현 현황과 재개 절차

## 최신 사용자 확인: 자연어 초안 → 승인 → 실제 티켓 생성

2026-09-07 사용자 제공 화면 텍스트와 승인·생성 확인을 확보했습니다. 대상 INC-014 / Platform / P1, 생성 티켓 32438f98-95ee-4385-a770-c03af381351d. 자연어 요청·업무 조회·RAG 근거·LLM 초안·검토·사람 승인·티켓 결과 표시의 대표 시연 흐름이 확인됐습니다. 이 항목은 사용자 확인이며 별도 티켓 API 재조회 결과와 구분합니다.

원문 대조: Gateway → Load Balancer → Firewall 점검, 결과/관측 시각 기록, 승인 후 티켓 생성은 합성 매뉴얼과 부합합니다. '추가 이상 징후가 발견되면 즉시 보고'는 인용된 원문에 명시되지 않은 추가 문구입니다. 생성/승인 기능 성공과 주장별 근거 충실도를 구분하며, 추가 지시·의무를 만들지 않도록 하는 품질 개선/평가 항목으로 남깁니다. 승인된 기존 티켓은 변경하지 않았습니다.

M3 핵심 대표 시연은 확인됐으나 자연어 기간 추출·자동 백그라운드 복구·실제 응답 유실 강제 주입 및 M4 품질/운영 검증까지 전체 완료로 표시하지 않습니다.

## 2026-09-07 초안 화면 오류 조사 중

사용자 화면의 자연어 초안 실패를 조사했습니다. 현재 AI API는 연결 거부, Docker 엔진 파이프는 없음 상태여서 실제 LLM 응답을 재현하지 못했습니다. 캡처 당시 원인은 아직 확정하지 않습니다. UI의 오류 코드별 안내/HTTP 상태/요청 ID 표시를 수정했고, Docker Desktop 실행 후 의존 서비스도 함께 기동해야 합니다.

```powershell
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag up -d --build --wait --wait-timeout 300 ai ui
```

기존 --no-deps를 제외해 postgres/business/chroma의 준비를 함께 확인합니다. 기동 후 새로고침·장애 재조회·AI 초안 미리보기를 재시도하고 실제 오류 코드 또는 성공 결과를 확인합니다.

## 최신: 자연어 기반 근거 초안 미리보기 코드 연결

`POST /v1/ticket-draft-previews`와 UI의 자연어 초안 폼을 추가했습니다. 사용자가 조회한 페이지에서 미해결 장애를 선택하고 요청을 입력하면 서버가 같은 조회 조건으로 장애를 다시 조회하고 역할에 맞는 매뉴얼 검색 후 기존 LLM Adapter의 연결로 초안을 생성합니다. 기간·대상 장애는 직접 선택하며 자연어 조건 추출은 아직 미구현입니다.

LLM은 제목·본문·사용 출처·보류 여부만 반환할 수 있습니다. 장애 ID·등급은 업무 조회 값, 담당팀은 합성 시연 정책 NETWORK→Platform/SERVER→Infrastructure/APPLICATION→Application으로 지정합니다. 초안에 실제 장애 사실과 출처 식별자를 함께 넣습니다. 출처의 실제 검색 결과 포함 여부·중복·응답 형식·입력 신원·해결 여부를 코드에서 확인하며, 주장별 근거 충실도 전체가 자동 보장되는 것은 아닙니다.

미리보기 API는 승인 원장/티켓을 등록하지 않습니다. UI의 '이 초안으로 승인 요청'을 누른 뒤 기존 영속 승인 흐름으로 들어갑니다. 근거 부족·모델 보류는 draft=null이며, LLM/출처 검증 오류는 실패로 표시하고 가짜 초안을 제공하지 않습니다. prompt_version=ticket-draft-v1, incident 조회 시각과 근거를 반환합니다.

검증 결과: 신규 초안 검사 19개를 포함한 API/그래프 회귀 75 passed(경고 1개), 전체 UI AppTest 9 passed(metadata 경고 711개). 미리보기에서 쓰기 없음, 선택한 장애의 재조회, 승인 플래그/임의 출처 거절, 이메일·전화 마스킹, 해결된 장애 차단, 보류 시 과거 초안 제거와 별도 승인 요청 버튼을 확인했습니다. LLM/HTTP는 모의 응답 기반이며 새 기능의 실제 제공자/컨테이너 검증은 대기입니다.

적용 명령(프로젝트 루트):

```powershell
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag up -d --build --no-deps --wait --wait-timeout 300 ai ui
```

성공 후 화면 새로고침 → 장애 조회 → '자연어로 초안 만들기'에서 INC-014 선택 → 'P1 네트워크 장애의 Gateway 점검 절차를 근거로 후속 티켓 초안을 만들어줘' → AI 초안 미리보기 → 원문 검토 → 이 초안으로 승인 요청 → 승인/거절. 새 이미지 적용이나 실제 초안 생성이 완료됐다고 아직 보고하지 않습니다.

## 최신: 거절 화면 실제 API 검증과 만료 화면 회귀 통과

`scripts/check_ticket_ui.py`를 실행해 실제 API를 사용하는 AppTest에서 초안 등록·대기 표시 → 거절 → 승인 버튼 제거 → 원장의 REJECTED와 ticket_id 없음, 총 4개 항목을 확인했습니다. 보고서 m3-ui-reject-20260906T135713256358Z.json, passed=true. 합성 거절 승인 1건을 남겼으며 기존 티켓은 변경하지 않았습니다.

`demo-ui/tests/test_tickets_ui.py`는 총 5 passed, 의존성 metadata 폐기 경고 395개입니다. 만료 실행 조회 시 승인/거절/재개 버튼 없음, 오래된 대기 화면에서 승인 실패를 성공으로 표시하지 않음, 새로고침 후 만료 표시를 모의 API로 검증했습니다. 서버 만료 차단은 기존 실제 PostgreSQL ApprovalIT에서 검증한 범위입니다. 운영 승인의 만료 시간을 단축하거나 DB 값을 변경하지 않았고, 실제 15분 경과를 기다리는 화면 검사는 수행하지 않았습니다.

브라우저 자동화 런타임은 sandbox ACL 초기화 오류로 연결하지 못했습니다. AppTest는 화면 요소/상호작용 검사이며 픽셀·레이아웃 시각 검증과 구분합니다. 다음 기능 구현 후보는 자연어/조회 근거에서 티켓 초안을 만들되 현재 승인 경계를 유지하는 연결입니다.

## 사용자 화면 확인: 승인 후 티켓 생성 완료

2026-09-06 사용자 제공 화면 텍스트에서 실행 4aa9b6cb-b6d8-461b-b211-23cab63d02bc가 '티켓 생성 완료'로 표시되고 티켓 377b9b70-d810-4e8c-976e-54d3be2b151a가 출력된 것을 확인했습니다. INC-014 / Platform / P1 수동 초안의 승인·생성 시연 성공에 대한 사용자 확인입니다. 브라우저를 직접 조작하거나 별도로 해당 티켓 API를 조회한 결과는 아닙니다. 거절 화면·만료 화면은 별도 수동 확인이 남아 있습니다.

수동 초안 기반 M3 핵심 시연 흐름은 연결됐습니다. 자연어 초안 생성, 자동 백그라운드 복구 및 응답 유실 강제 주입 통합 검증까지 전체 완료로 표시하지 않습니다.

## 최신 결과: 실제 티켓 실행 재시작 복구 통과

사용자 재시작 성공 보고서 m3-ticket-runs-20260906T134539158077Z.json의 기존 실행을 --after-restart로 직접 재개했습니다. m3-ticket-runs-20260906T134806256083Z.json: 준비 확인, 거절 실행 복원·거절·티켓 없음, 승인 실행 복원·승인·티켓 생성, 동시 중복 결정 8개 모두 통과입니다. 기존 등록/멱등/권한 검사 8건과 재시작 성공 기록까지 연계해 전체 흐름을 확인했습니다. 검사 명령/준비 대기 오류 이력은 지우지 않고 유지합니다.

현재 실행 API·PostgreSQL·Spring·LangGraph의 실제 대기 복구와 사람 결정 이후 티켓 생성이 검증됐습니다. 다음은 실제 브라우저 승인/거절 화면 확인입니다. 자연어 초안 생성·자동 백그라운드 복구·응답 유실 강제 주입 통합 검증은 아직 남아 있습니다. 아래 실패/검증 대기 기록은 이전 이력입니다.

## 최신 검사 중단 수정 — 기존 실행 재사용

m3-ticket-runs-20260906T134011270514Z.json: 등록/멱등/권한 검사 8건 통과 후 검사기 restart 명령의 rag 프로필 누락으로 실패했습니다. `--profile rag` 추가와 보고서 재개 옵션을 구현했고 회귀 2개 검사가 통과했습니다. 이미지 재빌드 없이 프로젝트 루트에서:

```powershell
uv run --no-sync python scripts/smoke_ticket_runs.py --restart --resume-report eval/results/m3-ticket-runs-20260906T134011270514Z.json
```

새 실행 2건을 등록하지 않고 기존 실행으로 재시작 이후 검사를 이어갑니다. 원본 실패 보고서는 유지합니다. 15분 승인 만료가 지났다면 restore 검사에서 멈출 수 있으며 만료 상태를 먼저 확인합니다. 실제 재개·승인·티켓 완료는 아직 검증 전입니다.

## 최신: 실제 티켓 그래프 실행 API·승인 화면 코드 연결

SpringLedger, TicketRuntime, ticket-runs API, Streamlit 초안/승인/거절/최근 실행/재개 화면을 추가했습니다. PostgreSQL agent.ticket_runs에 서버 UUID와 소유자+멱등 키·초안을 저장하고, 실행별 DB 세션 잠금으로 중복 재개를 차단합니다. 그래프는 실제 Spring 원장 API와 PostgreSQL checkpointer를 사용합니다. 결정/원장/체크포인트의 부분 실패는 같은 실행으로 재개하며 GET 조회가 티켓을 생성하지 않습니다. 준비 상태에 agent DB를 포함했습니다.

현재 초안은 직접 작성하는 로컬 운영자 시연입니다. 자연어 초안 생성·최종 query 기반 runs·백그라운드 자동 복구는 미구현입니다. 기본 M2 화면에는 새 기능이 나타나지 않고 compose.m3-app.yaml을 추가해야 합니다.

검증: 별도 work/m3-verify 환경에서 기존 조회·승인 API, 신규 실행 API 16개, 실제 LangGraph를 합쳐 56 passed/경고 1개. 기존 사용자 .venv에서 신규 Streamlit AppTest 2 passed/의존성 metadata 폐기 경고 158개. AppTest는 모의 HTTP 결과를 사용하는 화면 요소 검사이며 브라우저 시각 검증이 아닙니다. 실제 DB의 소유권 쿼리·잠금·전체 티켓 재시작 흐름은 새 컨테이너 적용 후 검증해야 합니다.

프로젝트 루트의 사용자 PowerShell에서:

```powershell
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag up -d --build --no-deps --wait --wait-timeout 300 ai ui
```

성공 후:

```powershell
uv run --no-sync python scripts/smoke_ticket_runs.py --restart
```

이 검사는 합성 실행·승인 2건과 티켓 1건을 생성하고 AI를 재시작합니다. 준비 후 대기 상태를 조회하고 거절/승인 및 동시 결정 재전송을 검사합니다. eval/results/m3-ticket-runs-*.json에 결과를 남깁니다. 아직 실행하지 않았으며 통과로 보고하지 않습니다. 기존 DB/검색 volume은 삭제하지 않습니다.

화면 검사는 localhost:8501의 '후속 티켓 승인'에서 초안 등록 → 승인 대기 → 승인/거절 → 결과 확인 순서입니다. 최근 실행 목록에서 재시작 전 실행을 다시 열 수 있습니다.

## PostgreSQL 체크포인트 — 별도 프로세스 저장·재개 검사 통과

최신 결과: 사용자 Docker 검사 보고서 `eval/results/m3-checkpoint-20260906T092634442073Z.json`을 직접 확인했습니다. build/pause/resume 모두 통과했고 passed=true입니다. 검사 전용 그래프의 interrupt 상태를 PostgreSQL에 저장하고 프로세스 종료 후 다른 컨테이너에서 재개했으며 agent 계정/스키마 격리 조건도 확인했습니다. 아래 실제 DB 검사 대기 문구는 이전 이력입니다. 전체 티켓 그래프·Spring 원장·runs API·화면을 결합한 복구 검증은 아직 남아 있습니다.

`app/agent/checkpoints.py`에 AsyncPostgresSaver 연결을 추가했습니다. agent_app/agent 스키마를 강제하고 business 스키마 USAGE가 없어야 기동합니다. autocommit·dict_row·명시적 직렬화 허용 목록과 setup migration 잠금을 적용했습니다. 운영 FastAPI lifespan 연결과 runs 소유권/동시 실행 통제는 아직 남았습니다.

공식 배포의 langgraph-checkpoint-postgres 3.1.2를 선택하고 기존 M2 패키지 버전을 제약으로 requirements-m3.lock을 생성했습니다. psycopg[binary] 3.3.5 등이 고정됐습니다. 기존 .venv 설치는 METADATA 접근 거부로 실패했으나 별도 work/m3-verify 환경에 해시 검증 설치 성공, 체크포인터 import·상태 직렬화·Ruff 검사를 통과했습니다. 기존 .venv 의존성을 교체하지 않았습니다.

실제 PostgreSQL 확인은 프로젝트 루트에서:

```powershell
uv run --no-sync python scripts/verify_checkpoint.py
```

compose.m3.yaml의 일회성 checkpoint-check 이미지를 빌드하고 서로 다른 컨테이너에서 pause/resume을 실행합니다. 대기 상태는 agent DB에 남고 티켓은 만들지 않습니다. 기존 AI/UI 이미지는 변경하지 않습니다. 성공/실패는 eval/results/m3-checkpoint-*.json에 저장합니다. 전체 티켓 그래프와 실제 Spring 원장 복구 검증은 별도 후속 작업입니다.

잠금 재생성은 M2 lock의 `package==version` 행만 제약 파일로 추출한 뒤 `uv pip compile ai-service/requirements-m3.in --constraints work/m3-constraints.txt --generate-hashes --universal -o ai-service/requirements-m3.lock`으로 수행했습니다. 정상 설치에는 저장된 lock만 필요합니다.

공식 참고: [PostgreSQL 체크포인터 배포·연결 설정](https://pypi.org/project/langgraph-checkpoint-postgres/). 실제 DB 테스트 통과 전에는 영속성 완료로 표시하지 않습니다.

## 승인 그래프 코드 추가 — 테스트 저장소 검사 통과

최신 결과: 사용자 PowerShell에서 `test_ticket_graph.py` 8 passed in 4.15s를 확인했습니다. 아래 앱 수집 실패 이후 사용자 환경에서 실행 결과를 확보했습니다. 승인 흐름·원장 불일치 차단·동일 키 재시도에 대한 실제 LangGraph 검사는 통과했으며 PostgreSQL 영속성/프로세스 재시작 검증은 아직 남아 있습니다.

`app/agent/ticket_graph.py`에 초안 등록 → interrupt → Spring 원장 재조회 → 별도 티켓 생성 노드 → 완료 흐름을 추가했습니다. 재개 payload는 신호로만 사용하며 승인 결정은 하지 않습니다. 원장 소유자·실행 ID·초안 해시를 확인합니다. 티켓 재실행은 approval_id에서 유도한 동일 키를 사용합니다. 저장소를 필수 인자로 받으며 기본 메모리 저장소를 운영에 묵시적으로 선택하지 않습니다.

`tests_m2/test_ticket_graph.py`에 실제 LangGraph 검사 8개를 작성했습니다. 승인 전 쓰기 0건, 위조 재개 신호 차단, 승인/거절/만료, 원장 불일치, 응답 유실 후 같은 키 복구를 확인합니다. 테스트 저장소는 InMemorySaver이며 그래프 객체 재구성만 검사합니다. 프로세스 재시작이나 PostgreSQL 영속성을 검증하는 테스트가 아닙니다.

Ruff 통과. 앱에서는 langgraph.checkpoint.memory 파일 접근 거부로 pytest 수집 실패했습니다. 사용자 PowerShell의 프로젝트 루트에서:

```powershell
$testTemp = Join-Path (Get-Location) ('work\pytest-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync pytest ai-service/tests_m2/test_ticket_graph.py -q --tb=short -p no:cacheprovider --basetemp "$testTemp"
```

후속 필수 작업: 인증된 실제 Spring Ledger adapter, PostgreSQL checkpointer 의존성 잠금·설치와 agent 계정 연결, 서버 실행 ID/소유권·동시 재개 통제, runs API, 승인 화면, 프로세스 재시작 복구 검증. 현재 그래프는 실행 API에 노출하지 않았으며 운영 이미지에도 적용하지 않았습니다.

구현 참고: [LangGraph interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts), [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence). interrupt 이전 코드는 재개 시 재실행되므로 외부 쓰기는 별도 단계로 둡니다.

## 최신 결과 — 실제 승인·티켓 API 연동 통과

2026-09-06 사용자 실행 보고서 `eval/results/m3-smoke-20260906T085915011247Z.json`을 직접 확인했습니다. passed=true, 실제 FastAPI → Spring → PostgreSQL 검사 15/15 통과입니다. 미승인/거절 생성 차단, viewer 결정 차단, 승인 후 티켓 생성, 동일 키 재전송 동일 결과, EXECUTED 원장과 티켓 조회를 확인했습니다. 합성 승인 2건·티켓 1건이 남습니다. 아래 적용/실행 대기 기록은 이전 이력입니다.

Java 26개 및 FastAPI 모의 HTTP 검사 32개와 구분해 기록합니다. 다음 작업은 LangGraph 승인 interrupt·영속 체크포인트·재개와 Streamlit 승인 화면입니다. 자연어 초안 생성, 재시작/응답 유실 복구, 전체 화면 시연은 아직 완료하지 않았습니다.

2026-09-06: 사용자 결정으로 M2 핵심 기능을 유지하고 M3를 시작했습니다. M2 추가 품질/운영 검증은 M4로 이월합니다. M2 전체 완료나 M3 완료를 의미하지 않습니다.

## 첫 단계 — Spring 승인·티켓 원장

코드 작성: V2 migration(approvals/tickets/ticket_idempotency/audit_events), 승인 생성·조회·결정, 티켓 생성·조회 API를 추가했습니다. 서비스 토큰 검증을 거친 사용자와 역할만 사용합니다. AI는 업무 DB에 접근하지 않습니다.

- PENDING → APPROVED 또는 REJECTED, 만료 시 EXPIRED, 생성 성공 시 EXECUTED.
- 승인 소유자·초안 해시·만료·미해결 장애를 확인한 뒤 서버 저장 초안으로 티켓을 만듭니다.
- 승인 행 잠금과 티켓의 approval_id UNIQUE로 중복 생성을 방지하도록 구현했습니다. 잠금 획득 후 별도 쿼리로 기존 티켓을 읽습니다.
- 사용자별 Idempotency-Key 재시도는 기존 결과를 반환하고 다른 요청에 키를 재사용하면 409입니다.
- 티켓·승인 전환·감사·멱등 결과는 같은 트랜잭션입니다. 만료 판정은 409 응답에도 원장에 유지합니다.
- 첫 단계에서는 run_id당 초안이 불변입니다. 버전 변경은 PROPOSAL_IMMUTABLE, 내용 변경은 PROPOSAL_CONFLICT입니다. 수정하려면 새 실행이 필요합니다. 최종 설계의 버전 교체/기존 승인 무효화는 아직 구현하지 않았습니다.

## 검증 상태

2026-09-06 17:42 사용자 PowerShell에서 `mvnw.cmd verify -Pintegration` BUILD SUCCESS를 확인했습니다. 저장된 Surefire/Failsafe 보고서에서도 단위/API 20개(ApprovalApiTest 5, IncidentApiTest 3, IncidentQueryTest 12), PostgreSQL 통합 6개(ApprovalIT 5, IncidentIT 1), 총 26개 실패·오류·스킵 0건을 확인했습니다. 승인 관련 신규 10개가 모두 통과했습니다. 앱의 Maven/JAR 접근 제약은 남아 있지만 사용자 환경에서 코드와 DB 검증을 완료했습니다.

운영 컨테이너 재빌드와 V2 운영 DB 적용은 아직 수행하지 않았습니다. 기존 M2 화면에서 승인 버튼은 나타나지 않습니다.

## 다음 실행

### 실제 서비스 적용·연동 검사 준비

`scripts/smoke_m3.py`를 추가했습니다. 로컬 AI → Spring → PostgreSQL에서 준비 상태, 합성 INC-014 조회, 미승인 티켓 차단, viewer 결정 차단, 거절 후 차단, 승인 후 생성, 동일 키 재시도 동일 티켓, EXECUTED 원장과 티켓 조회를 검사합니다. 실행마다 합성 승인 2건과 티켓 1건이 남습니다. 실패 시 자동 재시도/삭제하지 않으며 실행·승인·티켓 식별자와 단계 결과만 eval/results/m3-smoke-*.json에 저장합니다. 토큰·본문·원시 오류는 저장하지 않습니다.

앱 Docker 엔진 접근은 거부됐습니다. 정적 검사와 --help 실행은 통과했으나 실제 연동 검사는 아직 실행하지 않았습니다. 사용자 PowerShell의 프로젝트 루트에서:

```powershell
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --build --no-deps --wait --wait-timeout 300 business ai
```

위 명령이 성공하고 두 서비스가 healthy인 경우에만:

```powershell
uv run --no-sync python scripts/smoke_m3.py --execute
```

Business 기동 시 V2 추가 테이블 migration이 적용됩니다. 기존 데이터 volume과 검색 적재는 유지합니다. 연동 검사가 통과하기 전에는 LangGraph/UI까지 완료했다고 보고하지 않습니다.

Docker가 동작하는 사용자 PowerShell에서 프로젝트의 business-service 디렉터리로 이동한 후:

```powershell
.\mvnw.cmd verify -Pintegration
```

위 검사는 통과했으므로 코드 변경 전에는 반복할 필요가 없습니다. 다음은 업무 서비스 재빌드·마이그레이션·실제 API 흐름 확인과 FastAPI 연결입니다. Testcontainers 검사에는 별도 임시 PostgreSQL을 사용했습니다.

## 후속 작업

### FastAPI 연결 코드 추가 — HTTP 모의 검사 통과

사용자 PowerShell 실행 결과: 기존 조회와 신규 승인 API 검사 총 32 passed, 1 warning in 3.23s. 경고는 Starlette TestClient가 사용하는 AnyIO BlockingPortal 별칭의 DeprecationWarning입니다. 아래 앱 수집 실패 이후 사용자 환경에서 검증을 확보했습니다. MockTransport 기반 검사이므로 실제 Spring 연결·컨테이너·화면 검증 완료를 의미하지 않습니다.

`app/approvals.py`를 추가했습니다. `/v1/approvals` 생성/조회/결정과 `/v1/tickets` 생성/조회가 인증된 Spring API로 전달됩니다. 사용자/역할 헤더는 서버 토큰 매핑 값으로 교체합니다. viewer 쓰기 차단, 추가 필드 거절, 멱등 키 필수, 알려진 상태 충돌 코드 전달, 원문 오류 비공개, 응답 스키마/승인 소유자 검증을 적용했습니다. 쓰기는 자동 재시도하지 않으며 승인 결정 API 자체는 티켓을 생성하지 않습니다.

중간 연결 API의 run_id는 호출자가 동일 재전송에 사용하며 Spring에서 소유권과 불변 초안에 결합합니다. 최종 `/v1/runs`의 서버 발급 ID/영속 실행과는 구분합니다. LangGraph interrupt/checkpointer와 승인 UI는 아직 추가하지 않았습니다.

`test_approvals.py` 16개 작성, Ruff 통과. pytest는 앱에서 orjson DLL 접근 거부로 수집 중 실패하여 통과 결과가 없습니다. 프로젝트 루트에서 다음 검증을 진행합니다.

```powershell
$testTemp = Join-Path (Get-Location) ('work\pytest-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync pytest ai-service/tests/test_api.py ai-service/tests/test_approvals.py -q --tb=short -p no:cacheprovider --basetemp "$testTemp"
```

통과 후 실행 컨테이너 반영·실제 API 확인을 진행합니다. 현재 이미지에는 새 FastAPI 코드가 적용되지 않았습니다.

1. 실행 컨테이너 적용·실제 API 확인, 승인·거절 경합 보완(현재 동시 생성 검사는 통과).
2. FastAPI 인증 경계에서 승인·티켓 API 연결.
3. LangGraph 초안 → interrupt → 승인 확인 → 별도 쓰기 노드, PostgreSQL 체크포인트와 재개.
4. Streamlit 초안·승인/거절·결과 화면.
5. 재시작·응답 유실·중복 클릭·만료·타인 요청의 전체 흐름 검증.

GitHub 업로드는 사용자 요청에 따라 보류합니다. 오류 기록은 [troubleshooting](troubleshooting.md), 이월 항목은 [남은 작업](remaining-work.md)을 참고합니다.
