# 실행 환경

루트 compose.yaml이 PostgreSQL, Business, AI, UI를 기동합니다. Chroma는 rag 프로필이며 명시적 합성 데이터 적재는 seed 작업으로 분리됩니다.

postgres/init.sh는 새 volume 최초 실행 시 business_app·agent_app 계정과 소유 스키마를 분리합니다. AI 서비스에는 business DB 접속 정보를 주입하지 않습니다. M1에서 agent 계정은 아직 사용하지 않습니다.

UI 127.0.0.1:8501과 AI 127.0.0.1:8000만 공개합니다. [실행 안내](../docs/runbook.md)에 실행·종료·검증 명령이 있습니다.
