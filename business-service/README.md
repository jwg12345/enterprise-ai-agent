# Business Service

Spring Boot 3.5.16 / Java 21 / Maven 3.9.11입니다. 공식 Maven Wrapper 3.3.4의 only-script 배포본을 사용합니다.

- incident: 조회 조건 검증, SQL 매개변수 바인딩, 정렬/페이지, 명시적 seed
- security: 내부 서비스 토큰 및 허용 사용자/역할 조합 검사
- common: JSON 오류 응답
- db/migration: Flyway incidents 생성
- src/test: 단위/API 검사 및 PostgreSQL Testcontainers 통합 검사

`mvnw.cmd test`(Windows) 또는 `sh mvnw test`(Linux/macOS)로 단위 검사합니다. 실제 DB 검증은 `verify -Pintegration`이며 Docker가 필요합니다. 실행은 [통합 안내](../docs/runbook.md)를 따릅니다.

M3 첫 단계로 approval 패키지와 V2 migration을 추가했습니다. 초안 저장·승인/거절·만료·소유권·해시 검사와 티켓 생성/조회, 멱등 키, 감사 기록을 구현했습니다. 승인 UI와 AI 실행 연결은 아직 없습니다. 현재 실행 컨테이너에 적용하거나 검증 완료한 상태는 아닙니다.

ApprovalApiTest는 인증·역할·입력·해시를 검사합니다. ApprovalIT는 PostgreSQL에서 미승인/거절/만료 차단, 소유권·해시·해결된 장애 검사, 동시 생성 1건, 감사 실패 시 롤백을 검사합니다. 테스트 코드는 작성했으나 앱의 JAR 접근 거부로 실행 결과를 확보하지 못했습니다. Docker가 동작하는 PowerShell에서 이 디렉터리로 이동해 `./mvnw.cmd verify -Pintegration`을 실행하세요. 테스트 DB는 Testcontainers가 별도로 생성합니다.

첫 단계에서는 run_id당 초안을 수정할 수 없습니다. 변경하려면 새 run_id로 요청합니다. 기본 만료는 900초이며 `APPROVAL_TTL_SECONDS`로 설정합니다. 상세 계약과 남은 작업은 [M3 현황](../docs/m3-status.md)을 참고하세요.
