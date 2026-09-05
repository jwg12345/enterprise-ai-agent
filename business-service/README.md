# Business Service

Spring Boot 3.5.16 / Java 21 / Maven 3.9.11입니다. 공식 Maven Wrapper 3.3.4의 only-script 배포본을 사용합니다.

- incident: 조회 조건 검증, SQL 매개변수 바인딩, 정렬/페이지, 명시적 seed
- security: 내부 서비스 토큰 및 허용 사용자/역할 조합 검사
- common: JSON 오류 응답
- db/migration: Flyway incidents 생성
- src/test: 단위/API 검사 및 PostgreSQL Testcontainers 통합 검사

`mvnw.cmd test`(Windows) 또는 `sh mvnw test`(Linux/macOS)로 단위 검사합니다. 실제 DB 검증은 `verify -Pintegration`이며 Docker가 필요합니다. 실행은 [통합 안내](../docs/runbook.md)를 따릅니다.

승인·티켓·감사 원장은 M3에서 구현합니다. 현재 서비스는 조회 및 명시적 합성 seed만 제공합니다.
