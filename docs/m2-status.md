# M2 구현 현황과 재개 절차

상태: **코드 작성 및 기본 환경 테스트 완료, 실제 M2 실행 검증 미완료**. 실행 중인 localhost 화면은 이전 M1 컨테이너입니다. 이번 작업에서 M2 이미지로 교체하지 않았습니다.

## 추가한 코드

- Markdown metadata 검증·섹션 분할·500 token chunk/80 token overlap
- BGE-M3 1024차원 dense embedding Adapter와 모델 commit revision 고정
- Chroma 권한 metadata 필터·cosine distance·완성된 인덱스의 원자적 전환
- LangGraph 입력 분기 → 선택적 업무 조회 → 문서 검색 → 답변/보류
- POST /v1/answers, 출처 검증, 검색 실패/LLM 실패 오류 응답
- Streamlit 질문 입력·근거 원문·거리·출처 표시
- LLM 미연결 extractive 모드와 설정형 compatible API Adapter

M2는 동기식 읽기 요청입니다. /v1/runs의 영속 실행·승인 계약은 M3에서 구현합니다. 이번 API는 실행 상태를 메모리나 DB에 장기 보관하지 않습니다.

자연어로 업무 조회 기간을 자동 해석하는 기능은 아직 없습니다. 문서 질문에 업무 데이터를 함께 쓰려면 API에 명시적 incident_filters를 전달합니다. UI의 새 질문 입력은 문서 검색만 호출합니다.

## 확인한 것과 확인하지 못한 것

기존 Python 환경에서 **37개 테스트 통과**, ruff·Python 문법 검사 통과. 새 테스트는 문서 형식/권한 필터/출처/거절/LLM 오류/화면 렌더링을 검사하며 tokenizer·embedding·Chroma·HTTP 응답은 대체 객체를 사용합니다.

**초기 기록 당시에는 실제 LangGraph 라이브러리 실행, BGE-M3 모델 다운로드/인코딩, Chroma와의 M2 통신, 실제 LLM 호출을 검증하지 못했습니다. 이후 LangGraph 2건은 통과했으며 모델·M2 통합·실제 LLM은 여전히 검증 전입니다.** 독립된 실제 그래프 테스트는 ai-service/tests_m2에 있으며 위 37건에 포함되지 않습니다. 검색 점수·정확도·관련성 임계값 보정·메모리 사용량도 미측정입니다.

이전 실행에서는 Docker와 패키지 저장소 접근이 거절됐지만, 2026-09-05 재개 작업에서는 권한 확대 승인 후 Docker 연결과 실제 패키지 설치에 성공했습니다. Python 회귀 37건, 실제 LangGraph 2건, ruff, 의존성 호환 검사, 문서 검사가 통과했습니다. Java 단위/API 15건 및 PostgreSQL 통합 1건도 통과했습니다. 모델 적재·M2 통합 검증은 아직 별도로 확인해야 합니다.

## 설치와 버전 잠금 재개

M1의 pyproject.toml과 uv.lock은 유지했습니다. M2 의존성은 ai-service/requirements-m2.in에 있으며 전이 의존성까지 해시를 포함한 requirements-m2.lock을 생성했습니다. CPU용 torch 2.14.0+cpu를 Windows에 설치했고 Docker 빌드에서도 같은 CPU 배포의 설치를 확인했습니다. 이미지 저장 완료 및 실제 모델 검증은 별도입니다.

work 폴더를 만든 뒤 아래 순서로 생성·설치합니다. 아래 절차는 이번 재개 작업에서 실행했습니다.

```sh
uv export --frozen --no-dev --no-hashes -o work/m1-constraints.txt
uv pip compile ai-service/requirements-m2.in --constraints work/m1-constraints.txt --generate-hashes --universal --torch-backend cpu --emit-index-url -o ai-service/requirements-m2.lock
uv pip install --python .venv/Scripts/python.exe --torch-backend cpu --require-hashes -r ai-service/requirements-m2.lock
```

마지막 명령의 Python 경로는 Windows용입니다. Linux/macOS는 .venv/bin/python을 사용합니다. 버전 충돌이 있으면 원인을 기록하고 호환 조합을 선택한 뒤 lock을 다시 생성합니다. CPU용 PyTorch 배포 선택과 이미지 크기를 확인한 뒤 모델을 적재합니다.

```sh
uv run --no-sync pytest ai-service/tests_m2 -q
uv run --no-sync pytest -q
```

## 모델·인덱스 준비

.env에 EMBEDDING_REVISION을 BAAI/bge-m3의 검증된 40자리 commit SHA로 설정합니다. main을 그대로 사용하지 않습니다. 모델은 일회성 ingest 작업에서만 다운로드하며 서버 기동은 local_files_only를 사용합니다.

재개 시 공식 모델 API에서 확인한 revision은 `5617a9f61b028005a4858fdac845db406aefb181`입니다. 로컬 .env에 설정했습니다. revision 조회 자체는 모델 추론 검증이 아닙니다.

M1 검증 때 Docker 엔진 메모리는 약 3.8GB였습니다. BGE-M3를 추가한 전체 구성의 메모리는 아직 측정하지 않았으며, 실제 적재 시 메모리 부족 여부를 먼저 확인해야 합니다.

```sh
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d postgres business chroma
docker compose -f compose.yaml -f compose.m2.yaml --profile rag build ingest ai ui
docker compose -f compose.yaml -f compose.m2.yaml --profile rag run --rm ingest
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --wait --wait-timeout 300 ai ui
python scripts/smoke_m2.py
```

RAG_MAX_DISTANCE 기본값 0.45는 초기 후보이며 보정되지 않았습니다. 실제 개발용 질문으로 관련/무관 문서 거리를 측정한 뒤 조정하고, 고정 평가셋으로 별도 확인해야 합니다. 실패한 무관 질문을 삭제하거나 모두 통과한 것처럼 기록하지 않습니다.

## 답변 모드

LLM_MODE=extractive가 임시 기본입니다. 실제 문서 검색 결과의 원문을 보여주며 **생성형 LLM 답변으로 표시하지 않습니다**.

compatible 모드를 선택하려면 LLM_BASE_URL, LLM_MODEL, LLM_API_KEY를 서버 환경 변수에 설정합니다. 비밀은 채팅이나 Git에 넣지 않습니다. 엔드포인트는 Chat Completions 형태의 JSON 응답을 지원해야 합니다. 제공자별 지원 여부와 실제 호출은 후속 확인이 필요합니다. HTTP 실패 때 extractive 답변으로 조용히 대체하지 않습니다.

인용 ID 검증은 출처 존재만 확인합니다. 답변의 모든 문장이 실제 근거로 지지되는지 여부까지 자동 보장하지 않으므로 실제 LLM 연결 후 근거 충실도 평가가 필요합니다.

## 완료 판정

실제 그래프 테스트, 모델 적재, M2 smoke, 브라우저 근거 표시, LLM 모드별 실패 처리 및 관련성 보정을 확인한 후 M2 완료로 변경합니다. 현재 README의 M2 상태는 진행 중입니다.

## 공식 API 참고

- [LangGraph 그래프 API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [BGE-M3 공식 모델](https://huggingface.co/BAAI/bge-m3)
- [Chroma embedding query](https://docs.trychroma.com/docs/querying-collections/query-and-get)
- [LangGraph 1.2.11 배포](https://pypi.org/project/langgraph/1.2.11/)
- [Sentence Transformers 6.0.1 배포](https://pypi.org/project/sentence-transformers/6.0.1/)


## 한도 중단 후 인계 기록
사용자 CLI 발췌에는 ingest/ai 이미지 Built가 확인됩니다. 실제 검색 성공과는 구분합니다. 전체 진행 및 GitHub 저장 절차는 [2026-09-05 진행 기록](progress-2026-09-05.md)을 참고하세요.

