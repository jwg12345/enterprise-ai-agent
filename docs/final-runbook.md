# 최종 로컬 시연 실행 안내

Python 3.12/uv와 Docker Desktop Linux 엔진을 사용합니다. Java 테스트를 호스트에서 실행할 때는 JDK 21이 필요합니다. 다음 신규 설치 절차는 구성 파일을 대조해 정리한 안내이며, 새 PC/빈 volume에서 이번 마무리 중 다시 실행하지는 않았습니다.

## 이미 실행했던 환경

기존 .env와 모델·DB volume을 유지합니다. 저장소 루트에서:

```powershell
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag up -d --wait --wait-timeout 300 ai ui
```

코드를 새로 받았을 때만 --build를 추가합니다. 기동 중 워밍업은 LLM을 호출하지 않습니다. 준비 후 [시연 UI](http://localhost:8501)를 엽니다. API 명세는 [FastAPI 문서](http://localhost:8000/docs)입니다.

## 처음 준비하는 환경

1. .env가 없을 때 `python scripts/init_env.py`로 로컬 데모 비밀을 만듭니다. 기존 파일에는 재실행하지 않습니다.
2. .env에 아래 비밀이 아닌 항목을 추가합니다. 실제 키는 로컬 파일에만 저장합니다.

```dotenv
EMBEDDING_REVISION=5617a9f61b028005a4858fdac845db406aefb181
LLM_MODE=compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini-2025-04-14
LLM_API_KEY=여기에_로컬_API_키
RAG_MAX_DISTANCE=0.503
RAG_QUERY_PREFIX="사내 IT 장애 운영 매뉴얼: "
```

모델 이름은 기존 검증 환경입니다. 신규 계정에서의 제공 여부는 실행 시 확인해야 합니다. 키 없이 검색 원문만 확인하려면 LLM_MODE=extractive로 설정합니다. 이 모드에서는 LLM 요약·자연어 초안을 생성하지 않습니다.

3. 저장소 루트에서 기반 서비스와 합성 데이터를 준비합니다.

```powershell
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag up -d --build --wait --wait-timeout 300 postgres business chroma
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag run --rm seed
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag build ingest ai ui
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag run --rm ingest
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag up -d --wait --wait-timeout 300 ai ui
```

최초 ingest는 공개 모델을 다운로드합니다. 8GB 노트북에서는 다른 프로그램의 메모리 사용과 기동 지연에 영향을 받을 수 있습니다. 캐시가 없는 첫 실행에 HF_HUB_OFFLINE=1을 설정하지 않습니다. 모델/인덱스 변경은 기존 검색 결과와 동일하다고 간주하지 않습니다.

## 종료

```powershell
docker compose -f compose.yaml -f compose.m2.yaml -f compose.m3-app.yaml --profile rag down
```

데이터 보존을 위해 -v를 붙이지 않습니다. .env 비밀번호 변경만으로 기존 DB 계정 비밀번호가 갱신되지는 않습니다.

## 개발 검사

```powershell
uv sync --frozen
uv pip install --python .venv/Scripts/python.exe --torch-backend cpu --require-hashes -r ai-service/requirements-m2.lock
uv pip install --python .venv/Scripts/python.exe --require-hashes -r ai-service/requirements-m3.lock
uv run --no-sync ruff check ai-service demo-ui scripts
uv run --no-sync pytest ai-service/tests ai-service/tests_m2 demo-ui/tests -q
uv run --no-sync python scripts/check_docs.py
```

Linux에서는 .venv/Scripts/python.exe를 .venv/bin/python으로 바꿉니다. Java는 business-service에서 `./mvnw.cmd verify -Pintegration`으로 검사합니다. 통합 테스트용 Docker가 필요합니다. 실제 LLM 평가·장애 주입 도구는 비용이나 합성 티켓 생성이 있으므로 일반 검사와 구분하며 최종 마무리에서는 반복하지 않습니다.
