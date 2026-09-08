"""기존 Docker 모델/인덱스에서 개발셋 후보 거리를 읽고 임계값을 제안합니다."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", "compose.yaml", "-f", "compose.m2.yaml", "--profile", "rag"]


def score(rows: list[dict], threshold: float) -> dict:
    positives = [r for r in rows if r["expected_sections"]]
    negatives = [r for r in rows if not r["expected_sections"]]

    def hit(row):
        selected = {(c["document_id"], c["section"]) for c in row["candidates"]
                    if c["distance"] <= threshold}
        return all((e["document_id"], e["section"]) in selected for e in row["expected_sections"])

    return {"threshold": threshold, "positive_total": len(positives),
            "positive_hits": sum(hit(r) for r in positives), "negative_total": len(negatives),
            "negative_false_retrievals": sum(any(c["distance"] <= threshold for c in r["candidates"])
                                              for r in negatives)}


def propose(rows: list[dict]) -> dict:
    distances = {c["distance"] for r in rows for c in r["candidates"]}
    if any(not math.isfinite(d) or not 0 <= d <= 2 for d in distances):
        raise ValueError("Invalid cosine distance")
    candidates = sorted({0.0, 0.45, 2.0} | distances)
    table = [score(rows, t) for t in candidates]
    eligible = [s for s in table if s["positive_total"] and s["negative_total"]
                and s["positive_hits"] == s["positive_total"] and s["negative_false_retrievals"] == 0]
    # 소수점 반올림으로 경계 사례를 탈락시키지 않습니다. 설정 적용은 별도 검증 후 수행합니다.
    chosen = min(eligible, key=lambda s: (abs(s["threshold"] - 0.45), s["threshold"])) if eligible else None
    return {"baseline_0_45": score(rows, 0.45), "recommended": chosen, "sweep": table,
            "decision": "candidate_requires_fixed_evaluation" if chosen else "no_perfect_threshold_on_dev"}


def diagnostic_cases(dev: list[dict], fixed: list[dict]) -> list[dict]:
    selected = [c for c in fixed if c["id"] in {"rag-fixed-05", "rag-fixed-12"}]
    if {c["id"] for c in selected} != {"rag-fixed-05", "rag-fixed-12"} or len(selected) != 2:
        raise ValueError("Missing regression cases")
    return [{**c, "variant": variant, "search_query": prefix + c["query"]}
            for variant, prefix in [("original", ""), ("context", "사내 IT 장애 운영 매뉴얼: ")]
            for c in dev + selected]


def worker(diagnose_misses: bool = False) -> dict:
    # Docker 내부에서만 기존 모델을 로드합니다. 운영 서버 객체/설정은 변경하지 않습니다.
    from app.rag.store import RagStore

    dataset = Path("/evaluation/rag-dev.jsonl").read_bytes()
    cases = [json.loads(line) for line in dataset.decode("utf-8").splitlines() if line.strip()]
    if len(cases) != 10 or any(not c["id"].startswith("rag-dev-") for c in cases):
        raise ValueError("Only the frozen development dataset is accepted")
    fixed_hash = None
    if diagnose_misses:
        fixed_bytes = Path("/evaluation/rag-fixed.jsonl").read_bytes()
        fixed_hash = hashlib.sha256(fixed_bytes).hexdigest()
        cases = diagnostic_cases(cases, [json.loads(line) for line in fixed_bytes.decode("utf-8").splitlines()
                                       if line.strip()])
    store = RagStore.from_env()
    _, manifest = store.active()
    store.max_distance = 2.0
    rows = []
    for case in cases:
        started = time.monotonic()
        results = store.search(case.get("search_query", case["query"]), "viewer")
        rows.append({"id": case["id"], "query": case["query"], "expected_sections": case["expected_sections"],
                     "variant": case.get("variant", "original"),
                     "search_query": case.get("search_query", case["query"]),
                     "duration_ms": round((time.monotonic() - started) * 1000),
                     "candidates": [{k: c[k] for k in (
                         "document_id", "section", "chunk_id", "distance", "index_version"
                     )} for c in results]})
        print(f"Distance capture {len(rows)}/{len(cases)}", file=sys.stderr, flush=True)
    if store.active()[1] != manifest:
        raise ValueError("Index changed during evaluation")
    analysis = ({"decision": "diagnostic_only_no_threshold_recommendation",
                 "variants": {v: score([r for r in rows if r["variant"] == v], 0.456)
                              for v in ["original", "context"]}}
                if diagnose_misses else propose(rows))
    return {"dataset_sha256": hashlib.sha256(dataset).hexdigest(), "manifest": manifest,
            "regression_dataset_sha256": fixed_hash,
            "role": "viewer", "cases": rows, "analysis": analysis,
            "limitations": ["개발셋과 기존 실패 사례를 사용한 진단; 독립 평가 아님" if diagnose_misses
                            else "개발 질문 10개만 사용; 고정셋 미실행", "임계값은 자동 적용하지 않음",
                            "권한 필터 적용 후 top 5 후보; LLM/Guardrail 경로는 검사하지 않음",
                            "근거 없는 질문의 주변 문서 검색도 false retrieval로 계산하는 보수적 기준"]}


def docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([*COMPOSE, *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def main(diagnose_misses: bool = False) -> int:
    state = docker("ps", "--status", "running", "--services")
    if state.returncode:
        print("Docker 접근 실패. Docker를 사용할 수 있는 프로젝트 PowerShell에서 실행하세요.")
        return 1
    running = set(state.stdout.split())
    if "chroma" not in running:
        print("Chroma가 실행 중이어야 합니다. 먼저 M2 서비스를 기동하세요.")
        return 1
    report = {"run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "status": "failed"}
    restore = "ai" in running
    try:
        if restore:
            print("후보 거리 측정을 위해 AI를 잠시 중지합니다. 측정 후 다시 기동합니다.", flush=True)
            if docker("stop", "ai").returncode:
                raise RuntimeError("ai_stop_failed")
        extra_mounts = (["-v", f"{(ROOT / 'eval/rag-fixed.jsonl').as_posix()}:/evaluation/rag-fixed.jsonl:ro"]
                        if diagnose_misses else [])
        result = docker("run", "--rm", "--no-deps", "--pull", "never", "-T",
                        "-v", f"{(ROOT / 'scripts/calibrate_rag.py').as_posix()}:/evaluation/calibrate_rag.py:ro",
                        "-v", f"{(ROOT / 'eval/rag-dev.jsonl').as_posix()}:/evaluation/rag-dev.jsonl:ro",
                        *extra_mounts, "-e", "HF_HUB_OFFLINE=1", "-e", "PYTHONPATH=/workspace",
                        "ingest", "/workspace/.venv/bin/python", "/evaluation/calibrate_rag.py", "--worker",
                        *(["--diagnose-misses"] if diagnose_misses else []))
        if result.returncode:
            report["worker_exit_code"] = result.returncode
            # 라이브러리 원시 로그 대신 고정 오류만 저장합니다.
            raise RuntimeError("distance_worker_failed")
        lines = [line.removeprefix("RAG_REPORT=") for line in result.stdout.splitlines()
                 if line.startswith("RAG_REPORT=")]
        if len(lines) != 1:
            raise RuntimeError("missing_worker_report")
        report.update(json.loads(lines[0]))
        report["status"] = "measured"
    except (RuntimeError, ValueError, OSError) as exc:
        report["error"] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    finally:
        if restore:
            print("기존 AI 서비스를 다시 기동하고 준비 상태를 확인합니다.", flush=True)
            report["ai_restored"] = docker("start", "--wait", "--wait-timeout", "300", "ai").returncode == 0
        else:
            report["ai_restored"] = None
        label = "rag-diagnostic" if diagnose_misses else "rag-calibration"
        target = ROOT / "eval/results" / f"{label}-{report['run_id']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"결과 저장: {target}")
    success = report["status"] == "measured" and report.get("ai_restored") is not False
    print("측정 완료; 설정은 변경하지 않았습니다." if success else "측정 또는 AI 복구 실패. 결과 파일을 확인하세요.")
    return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--diagnose-misses", action="store_true", help="개발셋과 검색 누락 2건의 원문/문맥 비교")
    args = parser.parse_args()
    if args.worker:
        print("RAG_REPORT=" + json.dumps(worker(args.diagnose_misses), ensure_ascii=False))
    else:
        raise SystemExit(main(args.diagnose_misses))
