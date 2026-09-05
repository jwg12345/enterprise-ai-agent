"""로컬 문서 링크와 합성 자료의 기본 무결성을 확인합니다. 서비스 테스트가 아닙니다."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    documents = []
    for folder, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'work', 'target', 'build', '__pycache__'}]
        documents.extend(Path(folder) / name for name in names if name.endswith('.md'))
    for path in documents:
        content = path.read_text(encoding="utf-8")
        if "\ufffd" in content:
            errors.append(f"Invalid Unicode: {path.relative_to(ROOT)}")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            target = target.split("#", 1)[0]
            if not (path.parent / target).exists():
                errors.append(f"Broken link: {path.relative_to(ROOT)} -> {target}")
    cases = [json.loads(line) for line in (ROOT / "eval/dataset.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate evaluation IDs")
    source_ids = set()
    for path in (ROOT / "data/manuals").glob("*.md"):
        match = re.search(r"^document_id: (.+)$", path.read_text(encoding="utf-8"), re.M)
        if match:
            source_ids.add(match.group(1).strip())
    for case in cases:
        for source in case["expected_sources"]:
            if source not in source_ids:
                errors.append(f"Unknown source: {source}")
    incidents = json.loads((ROOT / "data/fixtures/incidents.json").read_text(encoding="utf-8"))
    if len({item["id"] for item in incidents}) != len(incidents):
        errors.append("Duplicate incident IDs")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(documents)} Markdown files, {len(cases)} evaluation cases, {len(incidents)} incidents")


if __name__ == "__main__":
    main()
