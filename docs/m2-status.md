> 2026-09-08: 이 문서는 과거 개발 기록입니다. 현재 범위와 다음 작업은 [최종 정리](final-status.md)와 [남은 작업](remaining-work.md)을 우선합니다. 추가 성능 검사는 진행하지 않습니다.

# M2 구현 현황과 재개 절차

> 2026-09-06 결정: 핵심 검색·답변 기능을 유지한 채 M3로 이동합니다. 남은 독립 평가·품질·운영 검증은 M4로 이월했으며 완료 처리하지 않습니다. 다음 작업은 [M3 진행 현황](m3-status.md)을 따릅니다. 아래 기록은 M2 이력입니다.

## 최신: 수정 컨테이너 실제 API 회귀 30/30 통과

사용자가 AI 이미지 Built/Healthy를 확인한 뒤 30건 전체를 실제 API로 재검증했습니다. 보고서 `eval/results/m2-rag-fixed-20260906T035159Z.json`: 30/30 통과, 답변 가능 18/18, 근거 부족 보류 12/12입니다. 이전 502였던 실제 IP/SLA/장애 건수 질문도 통과했습니다. 이번 실행은 추가 재시도 없이 30건을 순서대로 처리했습니다.

기존 실패를 사용해 수정했으므로 독립 평가가 아닌 회귀 결과입니다. 최초 25/30, 검색 개선 후 27/30, 보류 수정 후 30/30 보고서를 모두 보존합니다. M2 전체 완료는 아닙니다. 다음은 새 미사용 질문셋 평가 및 실제 답변 주장-근거 검토, 역할/장애/복구/성능, 최신 전체 pytest 확인입니다. GitHub 업로드는 보류입니다.

## 근거 부족 502 원인 재현·수정 — 컨테이너 적용 대기

실제 서비스에서 받은 합성 P1 근거를 사용해 같은 IP/SLA/장애 건수 질문을 호스트의 기존 Adapter로 진단했습니다. 네트워크 권한 승인 후 제공자 HTTP 200, abstain=true, answer 길이 0을 세 건 모두 확인했습니다. 기존 GroundedAnswer의 min_length=1 위반(string_too_short)이 재현됐습니다. 정확히 동일한 검색 후보를 캡처한 것은 아니므로 호스트 통제 재현과 원래 서비스 로그는 구분합니다. 키/제공자 원문은 진단 출력에 남기지 않았습니다.

제공자 입력용 스키마를 분리해 명시적 boolean abstain=true의 빈/공백 문구만 표준 근거 부족 안내로 정규화합니다. 출처 검증을 먼저 수행하며 잘못된 출처·중복 출처·false 보류의 빈 답변·필드 누락·null·HTTP 실패는 계속 오류입니다. 보류 사유를 요구하도록 프롬프트를 보완하고 버전을 m2-v2로 변경했습니다. 실제 오류를 extractive 성공으로 대체하지 않습니다.

새 보류/실패 검사 12건+분류 21건+검색 문맥 2건, 총 35건 통과 및 lint 통과. 실제 제공자와 수정 호스트 Adapter에서 세 건 모두 보류/비어 있지 않은 안내를 확인했습니다. 보고서는 `eval/results/abstention-adapter-20260906T034851Z.json`입니다. 이 검증은 배포된 전체 API 재검증이 아닙니다. 다음 명령으로 AI를 갱신하고 문제가 있던 3건과 정상 답변을 재검증합니다.

```powershell
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --build --no-deps --wait --wait-timeout 300 ai
```

전체 pytest의 최신 CLI 확인·새 미사용 질문 독립 평가·근거 충실도·권한/장애/복구/성능 검증은 남아 있습니다. GitHub 업로드는 보류입니다.

## 최신 실제 회귀: 문맥/0.503 적용 후 27/30

사용자 이미지 Built/AI Healthy 확인 후 기존 30건을 실제 API에서 재실행했습니다. `eval/results/m2-rag-fixed-20260906T034011Z.json`: 전체 27/30, 답변 가능 18/18, 근거 없음 9/12. 기존 검색 누락 rag-fixed-05/12와 정책 과차단 09/14/15는 모두 통과했습니다. 이 결과는 회귀 평가이며 새 독립 평가가 아닙니다.

새 실패는 rag-fixed-26(실제 Load Balancer IP), 27(SLA 제한 시간), 30(지난주 장애 건수)입니다. 세 건 모두 보류 대신 HTTP 502 ANSWER_FAILED를 반환했습니다. 오류 응답에는 내부 제공자/스키마/출처 실패 구분이 없으므로 정확한 원인은 아직 미확정입니다. 실제 사실을 지어낸 답변이 확인된 것은 아니며 API 오류로 실패했습니다. 설정 완화로 검색 누락은 해결됐지만 근거 부족 처리의 회귀가 있어 M2 완료나 최종 설정 검증 완료로 표시하지 않습니다.

다음은 합성 입력과 비밀 없는 오류 진단으로 ANSWER_FAILED 원인을 구분하고, 관련 문서는 있지만 질문의 정답이 없는 경우의 보류 응답을 수정하는 작업입니다. 최초 25/30과 현재 27/30 보고서는 모두 보존합니다. GitHub 업로드는 보류합니다.

## 문맥 진단 결과와 다음 후보 적용 준비

rag-diagnostic-20260906T033023Z.json에서 measured 및 AI 복구 성공을 확인했습니다. 0.456에서 원문 관련 6/8·무관 오검색 0/4, 문맥 추가 관련 7/8·무관 오검색 0/4입니다. 문맥 추가 후 남은 rag-fixed-05 정답 거리는 0.50295275, 무관 최소 거리는 0.5082075입니다.

공통 접두어 '사내 IT 장애 운영 매뉴얼: '와 임계값 0.503을 후보로 선택했습니다. 수집된 후보 재계산은 관련 8/8·무관 제외 4/4입니다. 여유 폭이 약 0.005로 좁으며 기존 실패 사례에 기반한 개선이므로 새 미사용 질문 평가가 반드시 남습니다. 실제 생성 답변 통과나 일반 정확도 향상으로 보고하지 않습니다.

RagStore의 검색 embedding 입력에만 선택적 RAG_QUERY_PREFIX를 추가했습니다. 원래 사용자 질문·매뉴얼·인용·ACL 필터는 유지합니다. 기본값은 빈 문자열이고 Compose에서 전달합니다. 로컬 .env에 인용부호로 끝 공백을 보존한 접두어와 0.503을 저장했습니다. 실제 컨테이너는 아직 이전 코드/설정입니다. 임베딩 입력·ACL·경계 필터 검사 2건과 분류/Agent 검사 21건, 총 23건 통과 및 lint 통과. 모델 재적재는 필요 없습니다.

다음 명령으로 AI 이미지/설정을 적용한 뒤 API 회귀를 진행합니다.

```powershell
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --build --no-deps --wait --wait-timeout 300 ai
```

문제가 생기면 RAG_QUERY_PREFIX를 비우고 RAG_MAX_DISTANCE=0.456으로 복구해 AI를 재생성합니다. GitHub 업로드는 보류합니다.

## 다음 작업: 검색 누락 2건 진단 모드

측정기에 --diagnose-misses를 추가했습니다. 개발 질문 10건과 이미 실패가 확인된 rag-fixed-05/12만 사용해 원래 표현과 공통 '사내 IT 장애 운영 매뉴얼: ' 접두어를 비교합니다. 총 24회 검색으로 관련 8건·무관 4건을 각 방식에서 검사합니다. 답이나 정답 섹션은 검색 입력에 넣지 않습니다. 기준 0.456에서 정답 검색/무관 오검색 건수를 비교하고 자동 추천/적용은 하지 않습니다. 독립 평가가 아닌 원인 분석입니다.

실행: `uv run --no-sync python scripts/calibrate_rag.py --diagnose-misses`. 기존처럼 AI를 잠시 멈췄다가 복구하며 모델 캐시를 재사용하고 OpenAI를 호출하지 않습니다. 결과는 eval/results/rag-diagnostic-*.json입니다. 실제 측정은 Docker 권한 있는 CLI 실행 대기입니다.

## 2026-09-06 재개: 정책 질문 실제 API 재검증 완료

readiness HTTP 200, M2/RAG/Business UP 확인 후 수정된 서비스에서 정책 질문 rag-fixed-09/14/15와 혼합 실행·금지 요청을 검사했습니다. 최초 정책 질문은 504 ANSWER_TIMEOUT(60813ms), 이어 2건은 503 RAG_UNAVAILABLE였지만 혼합/금지 요청은 각각 200 보류로 통과했습니다. 최초 결과는 `eval/results/policy-regression-20260906T032052Z.json`에 보존했습니다.

이후 정책 질문 3건을 한 번 재시도해 모두 HTTP 200 및 검색·정답 문서/섹션·인용·답변 조건을 통과했습니다. 결과는 `eval/results/policy-retry-20260906T032254Z.json`입니다. 자동으로 실패를 지우거나 최초 고정셋을 28/30으로 다시 계산하지 않습니다. 이번 검증은 수정 사례 3건의 회귀 검사입니다. 로컬 분류/Agent 연결 21건도 재통과했습니다. 전체 pytest의 최신 사용자 결과는 여전히 미확인입니다.

정책 질문 과차단 수정은 실제 API까지 확인했습니다. 다음은 검색 누락 rag-fixed-05/12 개선과 최초 60초 지연 원인·안정성 확인입니다. 검색 스레드가 timeout 이후 잠금을 유지했을 가능성은 코드와 부합하지만 Docker 로그/자원 접근이 거부돼 원인을 확정하지 못했습니다. 모델 재빌드·재적재·설정 변경은 하지 않았습니다.

## 최신 인계 — 사용자 크레딧 부족으로 중단

2026-09-06 사용자 출력에서 수정 AI 이미지 Built(8.7s), AI 컨테이너 Healthy(64.7s)를 확인했습니다. 정책 질문 분류 수정의 컨테이너 빌드/기동은 완료입니다. 최신 사용자 메시지에는 전체 pytest 결과가 없으므로 전체 테스트 통과를 추가로 확정하지 않습니다. 정책 질문 3건의 실제 API 재검증은 아직 실행하지 않았습니다.

사용자는 크레딧 약 4%로 12:19에 돌아오겠다고 했습니다. 추가 API 평가·Docker 작업·유료 호출 없이 중단합니다. GitHub 업로드는 계속 보류입니다. 별도 예약 작업은 생성하지 않았습니다.

재개 순서: readiness 확인 → 기존 실패 정책 질문 rag-fixed-09/14/15의 실제 답변·검색·출처 재검증 → 전체 pytest 결과 확인 → 검색 누락 rag-fixed-05/12 개선. 기존 fixed 질문은 개선에 사용했으므로 이후 결과는 회귀 검사로 보고합니다. 새로운 독립 평가와 권한·장애·복구·성능 검증은 남아 있습니다. 모델 재다운로드·재적재·이미지 재빌드를 먼저 반복하지 않습니다.

현재까지 확인: 최초 API 3/3, 기준 0.456 적용 후 개발셋 10/10, 최초 고정셋 25/30, 분류/Agent 연결 테스트 21건 통과, 평가기/측정기 10건·UI 2건 통과, 최신 코드/문서 검사 통과. M2 전체 완료는 아닙니다.

## 정책 질문 분류 개선 — 코드 검증, 컨테이너 적용 대기

guardrails.py로 분류를 분리하고 기존 answers.guard 호출 경로를 유지했습니다. 정책 문맥과 질문/설명 종결이 함께 있는 경우 읽기로 허용합니다. 명시적 생성·삭제·실행 지시, 특정 INC 작업, 금지 입력은 먼저 차단하므로 설명을 덧붙인 혼합 요청은 허용하지 않습니다. 규칙 기반 한국어 데모 범위이며 모든 자연어 의도를 판별하는 보안 장치가 아닙니다. 실제 쓰기 도구가 없는 M2 구조는 유지합니다.

정책 5건·실행/혼합 12건·금지 우선 3건 및 실제 Agent route 연결 1건, 총 21건 통과했습니다. 별도 평가기/측정기 10건·UI 2건도 통과했습니다. 전체 pytest는 앱의 orjson DLL 접근 거부로 수집 실패했습니다. 기존 사용자 41건 통과와 이번 전체 미검증을 구분합니다. lint 통과, 실제 컨테이너는 아직 이전 코드입니다.

프로젝트 PowerShell에서 전체 테스트 확인 후 AI만 빌드/재생성합니다. 모델 재적재는 필요 없습니다.

```powershell
$testTemp = Join-Path (Get-Location) ('work\pytest-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync pytest -q --tb=short -p no:cacheprovider --basetemp "$testTemp"
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --build --no-deps --wait --wait-timeout 300 ai
```

테스트 통과 후 기동합니다. Healthy 후 기존 고정셋 실패 3건의 실제 API 경로를 재검증해야 합니다. 이 셋을 바탕으로 수정했으므로 이후 실행은 회귀 검사입니다. 검색 누락 2건과 신규 미사용 평가셋 검증은 남아 있습니다.

## 최신: 개발셋 10/10, 최초 고정셋 25/30

사용자 보고서 m2-rag-dev-20260905T230421Z.json에서 보정 후 개발셋 10/10을 확인했습니다. 이어 기존 0.456 기준을 바꾸지 않고 별도 고정 질문 30건을 실제 compatible API로 실행했습니다. 결과 m2-rag-fixed-20260905T230558Z.json은 25/30 통과(답변 가능 13/18, 근거 없음 보류 12/12)입니다. 검색 누락 2건과 정책 질문을 쓰기로 분류한 것으로 판단되는 3건을 확인했습니다.

상세 증거·분모·한계는 [최초 품질 보고서](../eval/results/m2-quality-baseline.md)에 저장했습니다. 다음은 정책 설명/실행 의도 분리와 검색 누락 개선입니다. 실패한 고정셋을 개선에 사용한 뒤에는 회귀셋으로 취급하고 새 미사용 질문으로 독립 평가합니다. 고정셋 통과·M2 전체 완료로 표시하지 않습니다.

## 거리 측정 완료와 0.456 후보 선택

사용자 측정 보고서 `eval/results/rag-calibration-20260905T225705Z.json`에서 status=measured, ai_restored=true를 확인했습니다. 기존 4 chunk 인덱스와 모델 revision을 유지했습니다. Gateway 질문의 정답 거리는 0.45596775로 기존 0.45를 초과해 제외됐습니다. 무관 질문의 최소 거리는 0.5144383입니다.

최소 통과 경계 0.45596775에 아주 작은 여유를 두어 0.456을 후보로 선택했습니다. 수집된 개발셋 후보를 이 값으로 재계산한 결과 관련 질문 6/6 검색·무관 질문 4/4 제외입니다. 이는 실제 생성 답변 재평가 결과가 아닙니다. 로컬 .env의 RAG_MAX_DISTANCE만 0.456으로 저장했고 Git 제외도 확인했습니다. 이미지 기본값 및 실행 중 컨테이너는 변경하지 않았습니다. 보정 완료 플래그는 아직 false입니다.

권한 있는 프로젝트 PowerShell에서 아래 명령으로 설정을 적용한 뒤 개발셋을 재검증합니다. 컨테이너 start만으로는 새 환경변수가 반영되지 않습니다.

```powershell
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --no-deps --wait --wait-timeout 300 ai
uv run --no-sync python scripts/evaluate_m2.py --split dev
```

개발셋 재검증 후 기준을 고정하고 별도 fixed 30건을 실행합니다. fixed 결과에 맞춰 같은 고정셋을 반복 튜닝하지 않습니다. M2 전체 완료는 아닙니다.

## 원시 후보 거리 측정 준비

scripts/calibrate_rag.py를 추가했습니다. 기존 AI를 잠시 멈추고 별도 컨테이너에서 개발셋 10건의 viewer 허용 검색 후보를 수집한 뒤 기존 AI를 다시 시작합니다. 운영 설정과 인덱스는 변경하지 않습니다. 측정 결과에는 모델/인덱스 manifest·개발셋 해시·후보 거리·임계값별 누락/오검색 건수를 기록합니다. 구분 가능한 임계값이 없으면 추천하지 않습니다. 유료 LLM 호출과 고정셋 사용은 없습니다.

측정기 경계값·겹친 거리·실패 후 AI 복구·Docker 접근 실패 시 서비스 미변경 테스트 4건 및 기존 평가기 6건이 통과했습니다. 실제 Docker는 앱에서 접근 거부되어 측정하지 못했습니다. `uv run --no-sync python scripts/calibrate_rag.py`를 권한 있는 프로젝트 PowerShell에서 실행한 후 `eval/results/rag-calibration-*.json`을 확인해야 합니다. 현재는 측정 준비 완료이며 보정 완료가 아닙니다.

## 검색 품질 기준선 — 개발셋 10건

2026-09-06 실제 API에 접속해 개발 질문 10건을 compatible 모드로 실행했습니다. 결과는 `eval/results/m2-rag-dev-20260905T224745Z.json`: 9/10 통과(답변 가능 5/6, 근거 없음 4/4). Gateway 다음 점검 대상 질문은 매뉴얼에 답이 있으나 citations가 비고 abstain=true여서 실패했습니다. 원시 검색 거리가 없으므로 정확한 탈락 거리·원인은 미확정입니다. RAG_MAX_DISTANCE 설정은 변경하지 않았습니다.

개발셋 10건과 별도 고정셋 30건을 추가했습니다. 실행기는 섹션 일치·반환 거리·인덱스 ID 및 행동별 분모를 기록합니다. 고정셋은 기준 조정 후 실행하도록 남겼습니다. 다음은 임계값 적용 전 검색 후보 거리 측정 → 개발셋의 오검색/누락 균형 확인 → 기준 고정 → 고정셋 실행입니다. 생성 답변 근거 충실도·권한·장애·복구·성능도 남아 있습니다.

## 2026-09-06 사용자 CLI 평가 결과

최신 사용자 CLI 재검증: **41 passed, 1 warning in 11.16s**. 아래 새 임시 경로·캐시 비활성화 명령으로 전체 기본 pytest가 통과했습니다. 기존 공용 임시 폴더의 권한을 바꾸지 않고 실행 경로를 분리해 문제를 해결했습니다. 경고 1건은 남았으며 최신 발췌에는 상세가 없습니다. 이 결과는 실제 LangGraph 별도 tests_m2 및 전체 M2 품질/장애 검증을 포함하지 않습니다. 아래 35 passed/6 errors는 해결 전 기록입니다.

실제 결과 파일 `eval/results/m2-20260905T223926Z.json` 확인: compatible 모드에서 초기 계약 평가 3/3 통과. 관련 답변·인용 검증, 무관 질문 보류, 금지 요청 거절을 확인했습니다. 각 지연은 15188/3234/32ms이며 p95나 성능 목표 달성의 증거가 아닙니다. Git commit은 null이며 서버 모델/인덱스 버전은 미수집입니다. M2 전체 품질 평가는 남아 있습니다.

사용자 전체 pytest 결과는 35 passed, 6 errors. 6건 모두 공용 임시 폴더의 접근 거부로 tmp_path 준비 중 실패했습니다. 기존 pytest 캐시에도 접근 경고가 있습니다. 앱의 이전 DLL 오류와 구분합니다. 프로젝트 안에 매번 새 임시 경로를 지정하고 캐시 플러그인을 끈 평가 실행기 테스트는 앱에서 4/4 통과했습니다. 사용자 CLI 전체 재검증은 아래 명령으로 진행합니다.

```powershell
$testTemp = Join-Path (Get-Location) ('work\pytest-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync pytest -q --tb=short -p no:cacheprovider --basetemp "$testTemp"
```

초기 API 평가를 다시 호출할 필요는 없습니다. 위 명령은 테스트용 새 하위 경로만 사용하며 기존 공용 임시 폴더의 권한을 변경하지 않습니다.

## 2026-09-06 평가 준비 재개

- 중단된 patch를 확인해 저장된 UI·평가 코드부터 이어갔습니다. scripts/evaluate_m2.py에 초기 RAG 2건·거절 1건 평가, 데이터셋 해시·Git commit·클라이언트 환경·지연·실패 및 전체/완료 분모 기록을 추가했습니다. DB 쓰기 건수를 응답만으로 판정하던 항목은 제거했습니다.
- 수동 M2 workflow에 평가 실행과 결과 artifact 보관을 추가했습니다. 실제 평가와 원격 실행은 미검증입니다.
- Streamlit 너비 옵션을 width="stretch"로 수정했습니다. 평가 부정/중단 검사 4건과 UI 검사 2건, 총 6건 통과. ruff·문서 검사 통과.
- 전체 pytest는 orjson DLL 접근 거부로 수집 단계에서 실패했습니다. Docker 엔진 접근도 거부됐으며 localhost:8000 readiness는 연결 거부였습니다. 실제 평가·재시작·품질 보정은 수행하지 못했습니다. 이전 CLI 성공과 이번 실행 환경은 구분합니다.
- 다음은 권한 있는 프로젝트 PowerShell에서 실행합니다. 모델 재적재는 필요하지 않습니다. GitHub 업로드는 보류입니다.

```powershell
$env:UV_CACHE_DIR='work\uv-cache'
docker compose -f compose.yaml -f compose.m2.yaml --profile rag up -d --wait --wait-timeout 300
uv run --no-sync pytest -q
uv run --no-sync python scripts/evaluate_m2.py
```

Healthy 확인 뒤 평가합니다. compatible 모드에서는 실제 LLM을 호출합니다. 3건 통과 후에도 개발셋/고정 평가셋, 권한·장애·복구·성능·근거 충실도 검증이 남으므로 M2 완료가 아닙니다.

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
