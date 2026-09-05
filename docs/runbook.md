# M1 실행 안내

## 준비

Docker Desktop의 Linux 컨테이너 엔진, Python 3.12 또는 uv가 필요합니다. Java를 호스트에서 테스트하려면 JDK 21을 설치합니다. 컨테이너 빌드는 JDK를 자체 제공합니다.

저장소 루트에서 실행합니다. LLM API 키와 BGE-M3 모델 다운로드는 M1에서 필요하지 않습니다.

```sh
python scripts/init_env.py
docker compose up --build -d --wait --wait-timeout 300
docker compose run --rm seed
python scripts/smoke.py
```

이미 .env가 있으면 init_env.py를 다시 실행하지 않습니다. 이 명령은 기존 파일을 덮어쓰지 않습니다. UI는 [localhost:8501](http://localhost:8501), AI API 문서는 [localhost:8000/docs](http://localhost:8000/docs)에서 확인합니다. DB와 Spring은 호스트 포트를 열지 않습니다.

화면 기본 조건은 2026년 8월, P1, NETWORK입니다. seed 후 INC-014와 INC-015 두 건이 나옵니다. 합성 데이터만 사용하며 AI 응답·RAG·승인 UI는 아직 없습니다.

## 종료·재시작

```sh
docker compose down
docker compose up -d --wait --wait-timeout 300
```

일반 종료는 데이터를 보존합니다. seed를 반복해도 동일 ID는 추가하지 않고 기존 행도 덮어쓰지 않습니다. .env의 DB 비밀번호를 변경해도 기존 volume의 계정 비밀번호는 자동으로 바뀌지 않습니다.

## 테스트

uv 설치 후 Python 테스트:

```sh
uv sync --frozen
uv run ruff check ai-service demo-ui scripts
uv run pytest -q
uv run python scripts/check_docs.py
```

Java 단위 테스트(Windows는 mvnw.cmd, macOS/Linux는 sh mvnw):

```sh
cd business-service
sh mvnw -B test
sh mvnw -B verify -Pintegration
```

integration 프로필은 Docker가 필수입니다. Testcontainers가 별도 PostgreSQL을 생성해 Flyway migration·seed 멱등성·기간 경계·페이지를 검증하며, 데모 DB를 변경하지 않습니다. Docker 없이 실행하면 실패하며 자동 건너뛰지 않습니다.

## 준비 상태의 의미

M1 AI readiness는 Spring readiness(DB 포함)를 검사합니다. 응답에 stage=M1, rag=NOT_IMPLEMENTED를 표시합니다. Agent DB는 스키마·계정만 준비되었고 M1 코드에서 연결하지 않습니다.

Chroma는 후속 작업용 rag 프로필에 구성했습니다. 기본 실행에서 다운로드·기동하지 않습니다. 다음 명령은 저장소 기동만 하며 인덱스·임베딩이 준비되었다는 뜻이 아닙니다.

```sh
docker compose --profile rag up -d chroma
```

## 장애 확인

```sh
docker compose ps
docker compose logs --tail 80 business ai
```

업무 서비스 오류는 빈 조회 결과로 표시하지 않습니다. 인증 설정이 없거나 토큰이 중복이면 AI 기동이 실패합니다. 네트워크 제한 때문에 컨테이너 이미지/패키지 다운로드가 실패하면 연결을 확인한 뒤 같은 빌드를 재실행합니다.

운영용 공개 인증·TLS·문서 검색·티켓 생성은 M2 이후 범위입니다. 현재 로컬 UI는 서버에 저장된 조회자 토큰만 사용합니다.
