# API 계약 초안

M1~M3 구현 기준입니다. M1에서는 GET /v1/incidents, GET /api/v1/incidents와 health만 구현했습니다. 나머지는 설계 계약입니다. UUID 식별자는 서버가 생성합니다. JSON은 snake_case, 시간은 ISO 8601 offset 포함 형식입니다. 모든 API는 서버에서 인증·소유권/역할을 검증합니다.

## M1 조회 프록시

`GET /v1/incidents`는 Bearer 데모 토큰을 서버에서 viewer/operator로 매핑하고 Spring에 전달합니다. from/to는 필수이며 timezone offset을 포함합니다. severity/category/status는 선택입니다. page는 0~100000, size는 1~50입니다. 알 수 없는 필드와 중복 조건은 422로 거절합니다. 응답은 items/page/size/total이며 X-Request-ID 헤더를 반환합니다. 클라이언트의 사용자/역할 헤더는 전달하지 않습니다.

## AI Service

| 메서드·경로 | 요청 | 응답 |
|---|---|---|
| POST /v1/runs | query(1~4000자); Idempotency-Key 헤더 | 202: run_id, status, request_id |
| GET /v1/runs/{run_id} | 본인 실행 ID | 200: status, answer, incidents, citations, approval, ticket, error |
| POST /v1/runs/{run_id}/decisions | approval_id, decision(approve/reject); Idempotency-Key | 202: run_id, status; 최종 결과는 GET 조회 |
| GET /health/live | 없음 | 200: status |
| GET /health/ready | 없음 | 200 또는 503: status |

MVP는 polling 방식으로 결과를 조회합니다. POST 접수 후 프로세스 메모리에만 작업을 두지 않고 agent_runs에 저장합니다. 재시작 시 미완료 실행을 복원합니다. GET 응답의 `approval`은 대기 상태일 때만 승인 가능한 카드로 표시합니다. 재시도 응답은 현재 상태를 반환합니다.

실행 결과 예시(예시 ID는 설명용):

```json
{
  "run_id": "example-run",
  "status": "WAITING_APPROVAL",
  "answer": "INC-014는 미해결 상태입니다. 매뉴얼의 Gateway 점검 절차를 참고하세요.",
  "incidents": [{"id": "INC-014", "status": "OPEN"}],
  "citations": [{"document_id": "network-operations", "version": "1", "section": "P1 대응", "chunk_id": "index-generated-id", "distance": 0.21}],
  "approval": {"approval_id": "example-approval", "expires_at": "2026-09-05T00:15:00+09:00", "draft": {"incident_id": "INC-014", "title": "Gateway Timeout 후속 점검", "team": "Platform", "priority": "P1", "body": "Gateway 상태와 관련 로그를 확인합니다."}},
  "ticket": null,
  "error": null
}
```

distance는 설명용 값이며 측정 결과가 아닙니다. 실제 chunk_id는 적재 시 생성합니다.

## Business Service

| 메서드·경로 | 역할·요청 | 응답 |
|---|---|---|
| GET /api/v1/incidents | viewer 이상; severity, category, status, from, to, page, size | 200: items, page, size, total |
| POST /api/v1/approvals | operator; run_id, proposal_version, draft | 201: approval_id, draft_hash, expires_at, status |
| POST /api/v1/approvals/{id}/decision | operator/소유자; decision | 200: approval 원장 결과 |
| GET /api/v1/approvals/{id} | 소유자 | 200: status, draft_hash, ticket_id |
| POST /api/v1/tickets | operator/소유자; approval_id, draft_hash; Idempotency-Key | 신규 201, 재전송 200: ticket |
| GET /api/v1/tickets/{id} | 권한 있는 사용자 | 200: ticket |

티켓 내용은 서버 승인 원장의 draft에서 가져옵니다. 클라이언트가 새 제목/본문으로 덮어쓸 수 없습니다. 조회 시간 조건은 `[from, to)`이고 최대 조회 범위는 366일, size는 기본 20/최대 50, page는 0부터 최대 100000입니다. severity는 P1/P2/P3, category는 NETWORK/SERVER/APPLICATION, status는 OPEN/IN_PROGRESS/RESOLVED입니다. 알 수 없는 enum/역전 기간은 422입니다.

Idempotency-Key는 사용자·경로 범위에 결합합니다. 같은 키/동일 payload는 기존 결과, 같은 키/다른 payload는 409입니다. 요청 해시는 정규화한 JSON으로 계산합니다. 티켓 생성은 키가 달라도 approval_id UNIQUE로 단일 생성을 강제합니다. 동일 승인에 대한 재전송은 기존 티켓을 반환합니다.

## 공통 오류

```json
{"error":{"code":"APPROVAL_EXPIRED","message":"승인 요청이 만료되었습니다.","retryable":false},"request_id":"example-request"}
```

400 잘못된 JSON, 401 미인증, 403 역할 부족, 404 없는/다른 사용자 리소스, 409 상태·해시·멱등 충돌, 422 필드 검증, 429 제한 초과, 502 상위 API 실패, 503 미준비, 504 timeout을 사용합니다. 내부 stack trace·DB URL·토큰을 응답에 포함하지 않습니다. 다른 사용자의 실행 존재 여부는 404로 숨깁니다.

## M2 추가 API (코드 준비, 실제 실행 검증 대기)

POST /v1/answers: Bearer 인증, query(1~4000자), 선택적 incident_filters(M1 조회 필터와 동일). 동기식 200 응답이며 answer, citations(원문·문서 ID·버전·섹션·chunk ID·distance), source_ids, abstain, mode, request_id, steps, incidents를 반환합니다. 사용자 역할은 서버 인증에서 결정합니다.

M2 비활성화 시 503 RAG_NOT_ENABLED, 검색 실패 503 RAG_UNAVAILABLE, LLM/출처 검증 실패 502 ANSWER_FAILED, 시간 초과 504 ANSWER_TIMEOUT입니다. 쓰기 요청은 생성 없이 보류 응답으로 끝납니다. 이 API는 영속 runs/승인 API를 대체하지 않습니다.
