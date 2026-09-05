# 운영 요구사항

## 1. 실행 환경과 설정

로컬 Docker Compose 기반 시연을 목표로 합니다. 컨테이너는 UI, AI, Business, PostgreSQL, Chroma와 일회성 문서 적재 작업으로 분리합니다. 모델 캐시·DB·Chroma 데이터는 별도 volume으로 관리합니다. 외부 공개 배포는 현재 범위가 아닙니다.

M1 기준은 Python 3.12, Java 21입니다. Spring Boot·LangGraph·Chroma·모델 revision 및 모든 의존성은 구현 시 호환성을 확인해 lockfile/빌드 파일/컨테이너 태그에 고정합니다. `latest` 태그에 의존하지 않습니다. BGE-M3 첫 다운로드와 CPU 추론 비용을 감안해 메모리 16GB를 초기 실험 환경으로 가정하고 실제 사용량을 기록합니다. GPU는 필수 조건으로 두지 않습니다.

필요 설정: `APP_ENV`, `LLM_MODE`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `BUSINESS_API_URL`, `BUSINESS_SERVICE_TOKEN`, `DEMO_VIEWER_TOKEN`, `DEMO_OPERATOR_TOKEN`, `AGENT_DATABASE_URL`, `BUSINESS_DATABASE_URL`, `CHROMA_HOST`, `CHROMA_PORT`, `EMBEDDING_MODEL`, `EMBEDDING_REVISION`, `APP_TIMEZONE`, `DEMO_REFERENCE_TIME`, `APPROVAL_TTL_SECONDS`.

`.env.example`에는 이름과 비밀이 아닌 기본값만 둡니다. 필수 비밀 누락 시 기동/준비 상태 검사에서 실패합니다. 테스트 모드는 명시적으로 선택하며 실제 LLM 실패를 대체 응답으로 숨기지 않습니다.

## 2. 비기능 요구사항

| ID | 목표 | 검증 방법 |
|---|---|---|
| NFR-01 | 미승인 쓰기 0건, 동일 승인 중복 티켓 0건 | 부정·경합·재시도 통합 테스트 |
| NFR-02 | 재시작 후 대기 실행 복구 | interrupt 후 AI 재시작, 동일 실행 재개 |
| NFR-03 | 비밀·원문 개인정보 로그 0건 | 테스트용 민감 문자열 로그 검사 |
| NFR-04 | warmed-up 단건 답변 p95 15초 이내 목표 | 고정 환경, 동시 1명, 30건 이상; cold start 별도 |
| NFR-05 | LLM 제외 조회 API p95 500ms 목표 | 고정 seed와 환경에서 측정 |
| NFR-06 | 로컬 환경 재현 가능 | 새 volume에서 migration·seed·검색 적재·시연 |

이 수치는 서비스 보장이나 측정 결과가 아닙니다. LLM 공급자·장비·데이터량·동시성·표본 수를 결과에 함께 기록합니다.

## 3. 제한과 장애 처리

입력 최대 4,000자, 장애 조회 한 페이지 최대 50건, 검색 top-k 최대 10, Agent step 최대 12, 실행당 LLM 호출 최대 3을 초기 제한으로 둡니다. 원시 SQL·임의 URL·셸 실행 도구는 제공하지 않습니다.

Business 연결 timeout 2초/응답 5초, 검색 10초, LLM 30초, 승인 대기를 제외한 실행 60초를 초기값으로 둡니다. 읽기 요청의 일시 오류만 지수 backoff로 최대 2회 재시도합니다. 4xx는 재시도하지 않습니다. 쓰기는 같은 멱등 키와 원장 조회를 통해서만 복구합니다. 완료 여부 불명은 성공으로 표시하지 않습니다.

| 상황 | 처리·사용자 표시 |
|---|---|
| 문서 없음/검색 관련성 부족 | 정보 부족 표시, 대응 절차를 지어내지 않음 |
| Spring 장애 | 업무 조회 실패 표시, 티켓 생성 차단 |
| Chroma 또는 모델 준비 실패 | 준비 상태 실패; 실제 검색 결과로 위장한 대체 데이터 금지 |
| LLM timeout/할당량 초과 | 재시도 가능 오류 표시, 실행 기록 유지 |
| 승인 만료/권한 없음 | 409/403, 재승인용 새 초안 필요 |
| 생성 후 응답 유실 | RECONCILING 표시, 같은 승인·멱등 키의 기존 결과 확인 |
| DB 불가/감사 기록 실패 | 업무 쓰기 트랜잭션 롤백 |

## 4. 로그·헬스체크

JSON 로그 공통 필드: `timestamp`, `level`, `service`, `request_id`, `run_id`, `node`, `tool`, `duration_ms`, `status`, `error_code`, `prompt_version`, `model_version`, `index_version`, `token_usage`(제공될 때). 요청 ID를 AI → Spring으로 전달합니다. 토큰, 전체 질문, 원본 문서, LLM 원문 출력은 기본 로그에서 제외합니다. 디버그 원문 기록도 합성 데이터 환경에서만 명시적으로 허용합니다.

`GET /health/live`는 프로세스 생존만 검사합니다. `GET /health/ready`는 DB, Spring, Chroma, 활성 인덱스, 임베딩 준비를 제한 시간 내 검사하고 미준비면 503을 반환합니다. LLM 유료 호출은 health에서 수행하지 않습니다. Spring은 Actuator readiness/liveness를 사용하고 외부에는 상세 연결 정보를 노출하지 않습니다. Compose의 시작 순서 외에도 애플리케이션 재연결을 구현합니다.

관찰 항목은 요청 수·오류율·p50/p95 지연·도구 실패·승인 대기/만료·토큰 사용량입니다. 첫 MVP는 JSON 로그 집계와 평가 보고서로 충분하며 Prometheus/Grafana는 후속 확장입니다.

## 5. 테스트·CI

| 계층 | 필수 사례 |
|---|---|
| pytest 단위 | 날짜 범위, 입력/출력 스키마, 문서 분할, 근거 누락, 도구 차단, 승인 상태 분기 |
| pytest API/Agent | viewer 승인 거절, 다른 사용자 실행 접근 거절, LLM 오류, 검색 실패, interrupt 재개 |
| JUnit 업무 | 필터 검증, 승인 만료·거절, 초안 변조, 해결 완료 장애 거절, 멱등 키 충돌 |
| PostgreSQL 통합 | 동시 승인·티켓 생성 경합, UNIQUE 제약, 트랜잭션 롤백 |
| 전체 통합 | 승인 전 0건 → 승인 후 1건 → 재시도 후 1건; 재시작 복구; 응답 유실 복구 |

현재 CI는 문서 검사, Python lint/pytest, Java 단위·PostgreSQL 통합 테스트, Compose smoke를 구성했습니다. 원격 GitHub 실행 결과는 아직 없습니다. M3에서 승인·경합·복구 DB 테스트를 추가합니다. 테스트 모드에서는 외부 LLM 키나 모델 다운로드가 필요하지 않게 합니다. 실제 임베딩/LLM 평가는 별도 수동 workflow로 실행하고 키 없는 PR에서 실행하지 않습니다. 포크 PR에 비밀을 전달하지 않습니다. 모든 테스트를 건너뛴 초록색 빌드를 완료 증거로 사용하지 않습니다.

## 6. LLMOps 평가

현재 [평가 샘플](../eval/dataset.jsonl)은 8건의 초기 계약 사례입니다. M4에서 개발셋 10건, 고정 평가셋 30건 이상으로 나누고 문서 질문·업무 조회·복합 요청·근거 없음·공격 입력·승인 거절/만료를 포함합니다. 평가용 정답을 서비스 입력에 섞지 않습니다.

| 지표 | 정의 | 초기 통과 목표 |
|---|---|---|
| Retrieval hit@5 | 정답 문서가 top 5에 하나 이상 포함된 검색 질문 비율 | 0.85 이상 |
| Citation validity | 인용한 문서·chunk가 실제 검색 결과에 존재하는 비율 | 1.00 |
| Tool selection accuracy | 정답 허용 도구 집합과 실제 도구 집합이 일치한 사례 비율 | 0.90 이상 |
| No-evidence abstention | 근거 없는 질문에서 보류한 비율 | 1.00 |
| Approval safety | 미승인 쓰기 없는 부정 시나리오 비율 | 1.00 |
| Duplicate safety | 중복 요청에도 단일 티켓을 유지한 시나리오 비율 | 1.00 |

인용 존재 여부는 답변의 사실성을 증명하지 않습니다. 근거가 주장을 실제 지지하는지는 고정 루브릭으로 사람이 검토하며 정답 주장 수 대비 지지되는 주장 수를 별도 보고합니다. LLM judge는 선택적 보조 지표이며 안전성 테스트를 대체하지 않습니다. 검색 없는 사례는 retrieval 분모에서 제외하고 각 지표에 분모를 표시합니다.

평가 산출물은 `eval/results/`에 실행 ID, git commit, 환경, 데이터셋 해시, prompt/model/index 버전, 사례별 결과, 집계, 지연, 오류를 기록합니다. 실제 결과가 나오기 전에는 점수를 채우지 않습니다.

## 7. 보존·백업·복구

데모 기본 정책: 일반 로그 7일, Agent 상태 7일(대기 중 실행 제외), 감사 기록 30일, 업무 데이터는 명시적 데모 초기화 전까지 보존합니다. 이는 프로젝트 정책이며 법적 기준이 아닙니다. 삭제 작업은 상태·참조 무결성을 확인하고 승인 원장과 멱등 기록을 먼저 삭제하지 않습니다.

PostgreSQL 백업에는 business와 agent 상태를 같은 시점으로 포함합니다. 원본 문서와 인덱스 manifest를 보존하고 Chroma는 재색인으로 복구할 수 있게 합니다. 배포 전 migration을 검토하고 백업 후 적용합니다. 코드 롤백이 DB 다운그레이드를 의미하지 않습니다.

복구 시 서비스 중지 → DB 복원 → migration 호환성 확인 → 인덱스 복원/재색인 → readiness 확인 → 승인 원장 대조 → 시연 smoke test 순서로 검증합니다. volume 삭제를 일반 재시작 명령에 포함하지 않습니다.
