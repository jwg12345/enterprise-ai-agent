# M2 구현 현황과 재개 절차

상태: **실제 모델 적재·M2 기동·검색 smoke·실제 API 연동 화면 요소 검사 통과, M2 전체 완료는 아님**. localhost는 M2 AI/UI로 전환했습니다. 최신 결과와 남은 항목은 문서 마지막의 CLI 검증 결과를 확인하세요. 초기·앱 세션 기록은 당시의 검증 범위입니다.

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


## 앱 세션 재개 결과

GitHub 업로드는 사용자 요청으로 보류했습니다. 이 세션의 실제 그래프 테스트 2건은 uuid_utils DLL 접근 거부로 import 단계에서 실패했습니다. 이전 CLI 통과 기록과 실행 환경이 다릅니다. 모델 적재와 M2 통합 검증은 여전히 미완료이며 TS-014에 재현 내용을 기록했습니다.

## CLI 재개 중간 기록 (최종 결과는 아래 참조)

- GitHub 업로드 보류. 기존 AI/ingest 이미지 2.52GB 및 빌드 Completed를 직접 확인하여 재빌드하지 않았습니다.
- 현재 CLI에서 실제 LangGraph 2건이 재통과했습니다. 앱 세션의 uuid_utils DLL 접근 거부는 재현되지 않았고 앱 환경 자체의 해결 여부는 별도입니다.
- PostgreSQL·Business·Chroma 재기동 후 `docker compose -f compose.yaml -f compose.m2.yaml --profile rag run --rm ingest` 실행 중입니다.
- 고정 BGE-M3 모델 캐시 약 2.2GiB 다운로드와 391개 가중치 로딩 완료 출력을 확인했습니다. 적재 완료/활성 인덱스/M2 검색은 아직 미확인입니다.
- 인코딩 중 관측 메모리 약 2.55GiB, Docker 한도 약 3.7GiB입니다. 최고값이나 성능 벤치마크는 아닙니다.
- 실제 API 연동 화면 검사 `scripts/smoke_m2_ui.py`와 수동 workflow를 추가했고 ruff·문서 검사가 통과했습니다. 화면 검사 자체는 M2 기동 후 실행 예정입니다.
- 연결된 브라우저가 없어 브라우저 조작 도구는 No browser is available을 반환했습니다. AppTest 화면 요소 검사와 브라우저 시각 검증을 구분합니다.
- 다음 순서: ingest 성공 확인 → M2 ai/ui 기동 → seed → scripts/smoke_m2.py → scripts/smoke_m2_ui.py. M2는 아직 미완료입니다.

## CLI 검증 결과

### 완료한 작업

- 기존 AI/ingest 2.52GB 이미지 및 빌드 이력 Completed 확인. 이번 CLI 재개에서는 재빌드하지 않았습니다.
- `uv run --no-sync pytest ai-service/tests_m2 -q -p no:cacheprovider`: **2 passed**. 앱 세션의 uuid_utils DLL 접근 거부는 현재 CLI에서 재현되지 않았습니다. 앱 세션 자체의 권한 해결은 별도입니다.
- 고정 BGE-M3 모델 다운로드 및 로딩, 실제 1024차원 dense 인코딩, Chroma **4개 chunk 적재** 성공. 최종 ingest 종료 코드 0.
- 활성 collection: `manuals-c567565b8404-41987ec1`. revision: `5617a9f61b028005a4858fdac845db406aefb181`. manifest 차원 1024, count 4, chunk_size 500, overlap 80 확인.
- `docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --wait --wait-timeout 300 ai ui`: 종료 코드 0. AI/UI·Business/PostgreSQL 준비 상태 및 Chroma 기동 확인.
- 합성 seed 종료 코드 0, 신규 삽입 0건(기존 데이터 보존).
- `uv run --no-sync python scripts/smoke_m2.py`: **통과**. M2 readiness, 실제 매뉴얼 검색, 출처 ID 검증, 무관 질문 보류, 쓰기 요청 거절 확인.
- `uv run --no-sync python scripts/smoke_m2_ui.py`: **통과**. 실제 API 응답으로 INC-014/015 장애 표, 검색 원문·chunk·cosine distance·LLM 미연결 표시, 보류 시 이전 출처 제거를 확인했습니다. HTTP 응답을 대체하지 않았습니다.
- 실제 질문 “P1 네트워크 장애의 점검 순서를 알려줘”에서 network-operations / P1 대응 1개 출처, cosine distance **0.29285675**, mode=extractive, abstain=false를 관측했습니다. 추가 1회 호출은 578ms였으며 p95·성능 보장·정확도 지표가 아닙니다.
- 새 화면 검사 스크립트는 demo-ui README와 수동 `.github/workflows/m2-manual.yml`에 등록했습니다. 원격 CI 및 GitHub 업로드는 실행하지 않았습니다.

### 실패·해결 및 남은 경고

- 최초 ingest는 모델 준비 중 지연됐고 약 419MiB 스왑을 확인했습니다. OOMKilled=false였으며 지연 원인을 스왑 하나로 확정하지 않았습니다.
- 해당 적재 작업만 중지하고 캐시/volume을 보존했습니다. AI/ingest에 OMP_NUM_THREADS=2, MKL_NUM_THREADS=2를 설정하고 캐시를 사용하는 `run --rm -e HF_HUB_OFFLINE=1 ingest`로 재시도해 적재가 성공했습니다. 다운로드·실행 환경이 달라 정식 전후 성능 비교는 아닙니다.
- stop --time의 deprecated 경고: 이후 --timeout 사용. Sentence Transformers의 embedding dimension 메서드 이름 변경 경고와 Streamlit use_container_width 사용 중단 예정 경고는 아직 남아 있습니다.
- 연결된 브라우저가 없어 UI 자동화 도구가 No browser is available을 반환했습니다. AppTest는 화면 요소 검사이며 브라우저 픽셀·레이아웃 확인이 아닙니다.
- 문서 patch 일부는 문맥 불일치로 실패해 실제 파일 내용을 기준으로 다시 반영했습니다. Git diff는 실행 환경에 따라 저장소 미인식 오류가 있었으며 Git 변경·업로드로 이어가지 않았습니다.
- 상세 과정은 [TS-014/015](troubleshooting.md)를 참고합니다.

### 현재 남은 검증과 다음 작업

1. 연결 가능한 브라우저에서 [M2 화면](http://localhost:8501)을 열고 실제 배치·출처 펼치기·오류 표시를 시각 확인합니다.
2. 별도 개발셋으로 RAG_MAX_DISTANCE를 보정하고 고정 평가셋으로 확인합니다. 현재 0.45는 미보정이며 smoke의 무관 질문 1개 통과로 일반적인 검색 품질을 보장하지 않습니다.
3. 실제 문서의 역할별 허용 범위, 검색 장애·모델 불일치·재시작 복구를 실제 서비스 환경에서 추가 검증합니다. 현재 두 원본 문서는 viewer/operator 모두 허용합니다.
4. compatible LLM 제공자·모델·비밀을 서버 환경에 설정한 후 실제 호출·실패 처리·근거 충실도를 검증합니다. 지금은 extractive 원문 모드이며 생성형 LLM 연결은 검증하지 않았습니다.
5. 모델 메모리 최고값·장시간 안정성·cold/warm 지연·p95를 측정합니다. 이번 메모리 수치는 단일 관측이며 Docker 한도는 약 3.7GiB입니다.

현재 모델 적재·기동·smoke 작업은 종료됐고 M2 서비스는 실행 상태로 남겼습니다. 새 모델/문서가 없으면 재다운로드·재적재할 필요가 없습니다. 재개 시 아래 조회와 검사를 먼저 실행합니다.

```powershell
docker compose -f compose.yaml -f compose.m2.yaml --profile rag ps
uv run --no-sync python scripts/smoke_m2.py
uv run --no-sync python scripts/smoke_m2_ui.py
```

서비스가 중지돼 있을 때만 기존 모델/인덱스로 `docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --wait --wait-timeout 300`을 실행합니다. 캐시를 아직 받지 않은 새 환경에서는 먼저 일반 ingest로 모델을 준비하며 HF_HUB_OFFLINE=1은 이미 준비된 캐시에만 사용합니다. GitHub 업로드는 계속 보류합니다. **M2 또는 전체 MVP 완료로 표시하지 않습니다.**

## 사용자 화면 확인 및 OpenAI 연결 준비

- 사용자 제공 화면에서 P1 네트워크 질문의 P1 대응 원문·출처·거리 표시를 확인했습니다. 김치찌개 질문에서는 근거 부족 보류가 표시됐습니다. 두 사례의 시각 확인이며 검색 품질 전체 평가를 대신하지 않습니다.
- 사용자가 OpenAI API를 선택했습니다. 기존 compatible Adapter를 사용하고 로컬 설정에 OpenAI v1 주소와 gpt-4.1-mini-2025-04-14를 준비했습니다.
- LLM_API_KEY는 미설정입니다. 키 입력 전에는 extractive 모드를 유지하며 유료 호출이나 서비스 재기동은 하지 않았습니다. 키는 로컬 .env에만 입력합니다.
- 키 설정 후 LLM_MODE=compatible로 전환하고 AI 컨테이너를 재생성하여 실제 근거 답변과 실패 처리를 검증합니다. 모델 재적재는 필요하지 않습니다.
- 공식 모델 문서: https://developers.openai.com/api/docs/models/gpt-4.1-mini

## OpenAI 실제 호출 검증

- 저장된 키 값은 출력하지 않고 확인했습니다. 고정 gpt-4.1-mini-2025-04-14 모델의 연결 확인은 HTTP 200, 총 20토큰 사용으로 성공했습니다.
- 실제 실행 중인 검색 API의 P1 대응 근거를 받아 호스트의 기존 AnswerGenerator compatible Adapter에서 OpenAI를 호출했습니다. 한국어 대응 답변, abstain=false, 실제 chunk ID 인용 검증이 통과했습니다.
- 생성 답변은 Platform 팀 공유, Gateway/Load Balancer/Firewall 순서 점검, 결과·시각 기록으로 원문과 일치했습니다. 단일 사례 검증이며 전반적인 근거 충실도 평가는 남아 있습니다.
- 빈 근거는 Adapter가 보류하며 이 경로는 OpenAI를 호출하지 않습니다. 이번에는 별도 API 장애 주입 검증을 수행하지 않았습니다.
- 로컬 .env의 LLM_MODE를 compatible로 저장했습니다. Docker 접근 거부가 지속돼 컨테이너에 새 설정을 적용하지 못했습니다. 현재 실행 중인 API 응답은 여전히 extractive입니다.
- 권한이 있는 프로젝트 PowerShell에서 다음 명령을 실행한 뒤 화면 질문을 다시 제출합니다. 기존 모델·인덱스를 재사용하며 재빌드·재적재는 필요 없습니다.

```powershell
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --no-deps --wait --wait-timeout 300 ai
```

- 완료 기준: 실제 서비스 응답 mode=compatible와 한국어 답변·출처 확인. 현재는 호스트 Adapter 실제 호출까지만 검증했으며 컨테이너 전체 연결 완료로 표시하지 않습니다. GitHub 업로드는 보류입니다.

## 실제 AI 서비스 OpenAI 연결 확인

AI 컨테이너 재생성 후 실제 POST /v1/answers 요청이 HTTP 200, mode=compatible, abstain=false를 반환했습니다. 요청 ID: 27baf027-358b-422c-a0bc-832a9f49169f. P1 네트워크 질문에서 Platform 공유 → Gateway → Load Balancer → Firewall 점검과 결과·시각 기록을 설명했고 실제 검색 chunk ID를 반환했습니다. 컨테이너를 통한 생성 답변 연결을 단일 사례로 확인했습니다. 일반 검색 품질 보정·다양한 질문 평가·실패 처리 및 생성 모드의 브라우저 확인은 별도입니다. GitHub 업로드는 보류합니다.
