#Markdown 문서를 읽고 메타데이터를 검증한 뒤, BGE-M3로 임베딩할 수 있도록 청크(Chunk)로 분할합니다.
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

#Chunk 데이터 구조 정의
@dataclass(frozen=True)
class Chunk:
    id: str #청크를 구분하는 고유 식별자
    text: str #실제 검색 대상이 되는 문서 내용
    metadata: dict #문서 ID, 버전, 섹션, 접근 권한 등

# 매개변수	의미
# directory	Markdown 파일이 있는 디렉터리
# tokenizer	BGE-M3가 사용하는 토크나이저
# size=500	청크 하나의 최대 토큰 수
# overlap=80	인접 청크 간 중복 토큰 수
def load_chunks(directory: Path, tokenizer, size: int = 500, overlap: int = 80) -> list[Chunk]:
    if not 0 <= overlap < size: #청크 크기와 overlap 검증
        raise ValueError("Invalid chunk overlap")

    #Markdown 파일 탐색
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

        #권한 및 버전 검증 -> 문서에 접근할 수 있는 사용자 권한(viewr, operator) 검사
        roles = {role.strip() for role in fields.get("allowed_roles", "").strip("[]").split(",")}
        if not roles or not roles <= {"viewer", "operator"} or not fields.get("version"):
            raise ValueError("Explicit roles and version required")

        #합성 문서 확인
        if fields.get("synthetic") != "true":
            raise ValueError("Only synthetic demo documents accepted")

        #문서 해시 생성 -> SHA-256 해시 계산
        digest = hashlib.sha256(raw.encode()).hexdigest()
        #섹션별 분리
        section = "개요"
        for part in re.split(r"(^## .+$)", match[2], flags=re.M):
            if part.startswith("## "):
                section = part[3:].strip()
                continue
            #본문 정리
            body = re.sub(r"^# .+$", "", part, flags=re.M).strip()
            if not body:
                continue
            #BGE-M3 토크나이저 사용
            tokens = tokenizer.encode(body, add_special_tokens=False)
            for offset in range(0, len(tokens), size - overlap): #500토큰, 80토큰 중복 청킹
                text = tokenizer.decode(tokens[offset:offset + size], skip_special_tokens=True).strip()
                #청크 ID 생성 및 메타데이터 저장
                chunk_id = hashlib.sha256(f"{doc_id}:{digest}:{section}:{offset}".encode()).hexdigest()
                #문서 ID, 문서 해시, 섹션, 시작 토큰 위치를 조합해서 고유한 청크 ID를 만듭니다.
                chunks.append(Chunk(chunk_id, text, {
                    "document_id": doc_id, "version": fields["version"], "section": section,
                    "content_hash": digest, "source_path": path.name,
                    "allowed_viewer": "viewer" in roles, "allowed_operator": "operator" in roles
                })) # 이렇게 만든 청크 객체가 나중에 ingest()로 전달되고, BGE-M3 임베딩과 함께 ChromaDB에 저장
                if offset + size >= len(tokens):
                    break
    if not chunks:
        raise ValueError("No document chunks")
    return chunks
