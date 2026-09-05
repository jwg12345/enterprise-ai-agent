"""시연 Markdown의 제한된 front matter 형식을 검증해 chunk를 생성합니다."""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    metadata: dict


def load_chunks(directory: Path, tokenizer, size: int = 500, overlap: int = 80) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError("Invalid chunk overlap")
    chunks, document_ids = [], set()
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", raw, re.S)
        if not match:
            raise ValueError("Document metadata is required")
        fields = {}
        for line in match[1].splitlines():
            key, value = line.split(":", 1)
            if key in fields:
                raise ValueError("Duplicate metadata")
            fields[key] = value.strip().strip('"')
        doc_id = fields.get("document_id", "")
        if not re.fullmatch(r"[a-z0-9-]+", doc_id) or doc_id in document_ids:
            raise ValueError("Invalid or duplicate document ID")
        document_ids.add(doc_id)
        roles = {role.strip() for role in fields.get("allowed_roles", "").strip("[]").split(",")}
        if not roles or not roles <= {"viewer", "operator"} or not fields.get("version"):
            raise ValueError("Explicit roles and version required")
        if fields.get("synthetic") != "true":
            raise ValueError("Only synthetic demo documents accepted")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        section = "개요"
        for part in re.split(r"(^## .+$)", match[2], flags=re.M):
            if part.startswith("## "):
                section = part[3:].strip()
                continue
            # 제목만 있는 부분은 근거 chunk로 적재하지 않습니다.
            body = re.sub(r"^# .+$", "", part, flags=re.M).strip()
            if not body:
                continue
            tokens = tokenizer.encode(body, add_special_tokens=False)
            for offset in range(0, len(tokens), size - overlap):
                text = tokenizer.decode(tokens[offset:offset + size], skip_special_tokens=True).strip()
                chunk_id = hashlib.sha256(f"{doc_id}:{digest}:{section}:{offset}".encode()).hexdigest()
                chunks.append(Chunk(chunk_id, text, {
                    "document_id": doc_id, "version": fields["version"], "section": section,
                    "content_hash": digest, "source_path": path.name,
                    "allowed_viewer": "viewer" in roles, "allowed_operator": "operator" in roles
                }))
                if offset + size >= len(tokens):
                    break
    if not chunks:
        raise ValueError("No document chunks")
    return chunks
