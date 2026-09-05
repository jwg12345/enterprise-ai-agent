# 기업 업무 대응 AI Agent

사내 운영 문서와 장애 데이터를 함께 조회하고, 근거 있는 대응 방안을 제시하며, **사람의 승인 후 후속 티켓을 생성**하는 업무 지원 서비스입니다.

> 현재 단계: M1 조회 서비스 구현. Streamlit → FastAPI → Spring Boot → PostgreSQL을 연결했습니다. 실제 RAG·LangGraph·영속 승인·티켓 생성·LLM 평가는 M2 이후 범위입니다. 아래 전체 요구사항과 성능 수치는 최종 목표입니다.

## 1. 해결할 문제

IT 운영 담당자는 장애 기록, 운영 매뉴얼, 티켓 시스템을 오가며 정보를 찾습니다. 문서만 검색하는 챗봇으로는 현재 장애 상태를 확인하거나 후속 업무를 안전하게 처리하기 어렵습니다. 이 프로젝트는 문서 검색과 업무 API를 연결하고 변경 작업에는 승인·권한·감사 기록을 적용합니다.

가상 회사의 합성 데이터만 사용합니다. 실제 기업에서 운영 중인 서비스라는 의미는 아닙니다.

## 2. 대표 시나리오

> “2026년 8월의 P1 네트워크 장애를 찾아 원인을 요약하고, 운영 매뉴얼에 따른 대응 방안을 알려줘. 아직 해결되지 않았다면 후속 티켓도 만들어줘.”

1. Spring API에서 기간·등급·분류 조건으로 장애를 조회합니다.
2. BGE-M3 + ChromaDB로 관련 매뉴얼을 검색합니다.
3. 실제 장애 데이터와 문서 근거를 구분해 답변합니다.
4. 미해결 장애에 대해 티켓 초안을 보여주고 승인을 기다립니다.
5. 승인 권한과 초안 유효성을 확인한 후 Spring API가 티켓을 생성합니다.
6. 생성 결과와 요청 추적 ID를 표시합니다. 거절하면 생성하지 않습니다.

고정 시연 기준 시각은 `2026-09-05T00:00:00+09:00`입니다. “지난달”은 Asia/Seoul 기준 8월 1일 이상, 9월 1일 미만으로 해석하며 화면에 실제 검색 기간을 표시합니다. 일반 실행에서는 서버 시각을 사용합니다.

## 3. 사용자와 범위

| 역할 | 허용 작업 |
|---|---|
| 조회자(viewer) | 본인 권한 범위의 장애 조회·문서 기반 질문·실행 결과 조회 |
| 운영자(operator) | 조회 기능 + 본인이 요청한 티켓 초안 승인·거절 |

MVP는 단일 가상 조직의 IT 장애 대응에 집중합니다. 티켓 생성 이외의 DB 변경, 실제 서버 복구 명령 실행, 이메일·메신저 전송, PDF/OCR, 다중 조직, SSO, Kubernetes, 모델 학습은 후속 범위입니다. LLM 제공자와 모델은 구현 시 설정으로 선택하고, 테스트에서는 결정론적 대체 구현을 사용합니다.

## 4. 기능 요구사항과 인수 기준

| ID | 요구사항 | 완료를 판정하는 증거 |
|---|---|---|
| FR-01 | 자연어 요청에서 기간·등급·분류를 구조화 | 스키마 밖 값은 거절하고 모호한 기간은 확인 요청 |
| FR-02 | 장애 목록 조회 | Spring API의 필터·페이지 크기 제한 검증; LLM의 임의 SQL 금지 |
| FR-03 | 문서 검색 | 문서 ID·버전·섹션·chunk ID·검색 거리 반환; 허용 문서만 검색 |
| FR-04 | 근거 기반 답변 | 주요 대응 주장에 출처 제공; 근거 없으면 정보 부족 표시 |
| FR-05 | 티켓 초안 생성 | 장애 ID·제목·담당팀·우선순위·본문을 승인 전에 표시 |
| FR-06 | HITL | 승인 대기·승인·거절·만료 처리; 미승인/거절/만료 요청의 티켓 생성 0건 |
| FR-07 | 안전한 업무 변경 | 서버 권한 검사·초안 해시 결합·멱등성; 동시 승인/재시도에도 1건 |
| FR-08 | Guardrail | 입력 제한·도구 허용 목록·권한 필터·출력 검증; 검색 문서의 지시를 실행하지 않음 |
| FR-09 | Streamlit 시연 | 채팅, 장애 표, 출처, 승인 카드, 최종 결과, 실패 안내 표시 |
| FR-10 | 복구 및 추적 | 재시작 후 승인 대기 복원; UI 세션이 없어도 서버에서 본인 실행 조회 |
| FR-11 | 기본 LLMOps | 구조화 로그·헬스체크·버전 기록·오프라인 평가 결과 저장 |

## 5. 기술 구성

| 영역 | 선택 | 역할 |
|---|---|---|
| Demo UI | Streamlit | 질문·조회 결과·근거·승인 화면 |
| AI API | Python / FastAPI | 인증 경계, 실행 API, Agent 조정 |
| Agent | LangGraph | 명시적 상태 전이, 승인 중단·재개 |
| RAG | BGE-M3 / ChromaDB | 한국어 매뉴얼 임베딩·dense 검색 |
| 업무 서비스 | Java / Spring Boot | 장애 조회, 승인 원장, 티켓 생성, 업무 규칙 |
| 영속 저장소 | PostgreSQL | 업무 데이터 및 분리된 Agent 체크포인트 |
| 검증 | pytest / JUnit | AI 정책 및 업무 트랜잭션 검증 |
| 실행·CI | Docker Compose / GitHub Actions | 로컬 통합 환경 및 회귀 검사 |
| LLMOps | JSON 로그 / 평가 데이터 / health | 실패 추적, 품질·지연 측정 |

## 6. 목표 구조

```text
enterprise-ai-agent/
├── README.md
├── AGENTS.md
├── docs/
│   ├── architecture.md
│   ├── operations.md
│   ├── api-contract.md
│   ├── demo-scenario.md
│   └── implementation-plan.md
├── prompts/codex-first-task.md
├── ai-service/                 # FastAPI·LangGraph·RAG 구현 위치
├── business-service/           # Spring Boot 구현 위치
├── demo-ui/                    # Streamlit 구현 위치
├── data/manuals/               # 합성 매뉴얼
├── data/fixtures/              # 고정 시연 데이터
├── eval/                       # 평가 입력 및 결과 규격
├── infra/                      # DB 계정·스키마 초기화
├── scripts/                    # 문서 검증 도구
└── .github/                    # Python·Java·Compose CI·PR 템플릿
```

## 7. 문서 읽는 순서

1. 이 README: 요구사항과 완료 기준
2. [전체 Architecture](docs/architecture.md): 서비스 경계·Agent·RAG·데이터
3. [운영 요구사항](docs/operations.md): 장애 복구·보안·테스트·평가·배포
4. [AGENTS.md](AGENTS.md): 구현 작업 규칙
5. [Codex 첫 작업 프롬프트](prompts/codex-first-task.md): 첫 구현 범위와 검증

상세 [API 계약](docs/api-contract.md), [구현 순서](docs/implementation-plan.md), [시연 대본](docs/demo-scenario.md)도 함께 제공합니다.

## 8. 현재 사용 방법

Python 3.12와 Docker Desktop을 준비하고 저장소 루트에서 실행합니다. 최초 실행에서만 로컬 인증 설정을 생성합니다.

```sh
python scripts/init_env.py
docker compose up --build -d --wait --wait-timeout 300
docker compose run --rm seed
python scripts/smoke.py
```

[조회 화면](http://localhost:8501)에서 기본 조건으로 조회하면 INC-014와 INC-015가 표시됩니다. 자세한 실행·종료·테스트 명령은 [M1 실행 안내](docs/runbook.md)를 참고하세요. .env가 이미 있으면 init_env.py를 다시 실행하지 않습니다. LLM 키와 모델 다운로드는 아직 필요하지 않습니다.

## 9. 구현 단계와 포트폴리오 증거

| 단계 | 결과물 | 상태 |
|---|---|---|
| M0 | 요구사항·Architecture·운영·지침·첫 프롬프트 | 완료 |
| M1 | 서비스 기동·DB migration·조회 API·Compose·기본 테스트 | 완료 |
| M2 | 실제 BGE-M3 검색·LangGraph 답변·출처 UI | 코드 준비·실행 검증 대기 |
| M3 | 영속 HITL·권한·멱등 티켓 생성 | 예정 |
| M4 | 평가·장애 복구 검증·스크린샷·시연 영상 | 예정 |

구현 후 README에 실제 화면, 실행 환경, 측정된 평가 수치, 실패 사례, 설계 개선을 추가합니다. 통과하지 않은 CI 배지나 측정하지 않은 성능 수치는 게시하지 않습니다. 라이선스와 외부 모델·라이브러리 사용 조건은 공개 배포 전에 결정·확인합니다.

## 개발 과정과 개선 기록
[개선·문제 해결 기록](docs/troubleshooting.md)에 실제 오류의 원인, 해결 과정, 검증 결과를 누적합니다. 해결되지 않은 경고와 예방 개선도 구분해서 기록합니다.


실제 수행한 검증과 한계는 [M1 검증 결과](docs/validation-m1.md)에 기록했습니다. Python 17건, Java 단위/API 15건과 PostgreSQL 통합 1건이 통과했습니다.

## M2 진행 현황

[구현 현황과 재개 절차](docs/m2-status.md)에 코드 범위와 미검증 항목을 정리했습니다. 현재 37개 Python 테스트가 통과했지만, 실제 M2 의존성·모델·컨테이너는 실행 권한 제한으로 검증하지 못했습니다. localhost 화면은 이전 M1입니다.
