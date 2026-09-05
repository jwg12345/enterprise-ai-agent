import hashlib
import json
import os
import re
import threading
import uuid
from pathlib import Path


class RagUnavailable(Exception):
    pass


class RagStore:
    """서빙에서는 모델을 다운로드하지 않으며 완성된 인덱스만 사용합니다."""
    def __init__(self, model, client, revision: str, manifest: Path, max_distance: float):
        self.model, self.client, self.revision = model, client, revision
        self.manifest, self.max_distance = manifest, max_distance
        self.lock = threading.Lock()

    @classmethod
    def from_env(cls, allow_download=False):
        revision = os.environ.get("EMBEDDING_REVISION", "")
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise RagUnavailable("BGE-M3의 고정 commit revision이 필요합니다.")
        # 선택적 의존성을 기본 M1 기동 시 import하지 않습니다.
        import chromadb
        from chromadb.config import Settings
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("BAAI/bge-m3", revision=revision, device="cpu",
                                    cache_folder=os.environ.get("HF_HOME", "/model-cache"),
                                    local_files_only=not allow_download, trust_remote_code=False)
        model.max_seq_length = 1024
        if model.get_sentence_embedding_dimension() != 1024:
            raise RagUnavailable("Unexpected embedding dimension")
        client = chromadb.HttpClient(host=os.environ.get("CHROMA_HOST", "chroma"),
                                     port=int(os.environ.get("CHROMA_PORT", "8000")),
                                     settings=Settings(anonymized_telemetry=False))
        threshold = float(os.environ.get("RAG_MAX_DISTANCE", "0.45"))
        if not 0 <= threshold <= 2:
            raise RagUnavailable("Invalid cosine distance threshold")
        return cls(model, client, revision, Path(os.environ.get("INDEX_MANIFEST", "/index/active.json")), threshold)

    def active(self):
        try:
            manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
            if manifest["revision"] != self.revision or manifest["dimension"] != 1024:
                raise RagUnavailable("Index/model mismatch")
            collection = self.client.get_collection(manifest["collection"], embedding_function=None)
            if not collection.metadata.get("complete") or collection.count() != manifest["count"]:
                raise RagUnavailable("Index is incomplete")
            return collection, manifest
        except RagUnavailable:
            raise
        except Exception:
            raise RagUnavailable("Active index is unavailable") from None

    def ready(self):
        try:
            self.client.heartbeat()
            self.active()
            return True
        except Exception:
            return False

    def search(self, query: str, role: str):
        if role not in {"viewer", "operator"}:
            raise RagUnavailable("Unsupported role")
        # timeout 후에도 살아 있는 embedding thread가 자원을 중복 점유하지 않게 합니다.
        if not self.lock.acquire(blocking=False):
            raise RagUnavailable("검색 작업 중입니다. 잠시 후 다시 시도하세요.")
        try:
            collection, manifest = self.active()
            vector = self.model.encode([query], normalize_embeddings=True).tolist()
            found = collection.query(query_embeddings=vector, n_results=min(5, manifest["count"]),
                                     where={f"allowed_{role}": True},
                                     include=["documents", "metadatas", "distances"])
            citations = []
            for cid, text, metadata, distance in zip(
                found["ids"][0], found["documents"][0], found["metadatas"][0], found["distances"][0], strict=True
            ):
                if distance <= self.max_distance and metadata.get(f"allowed_{role}") is True:
                    citations.append({"chunk_id": cid, "text": text, "distance": distance,
                                      "document_id": metadata["document_id"], "version": metadata["version"],
                                      "section": metadata["section"], "index_version": manifest["collection"]})
            return citations
        except RagUnavailable:
            raise
        except Exception:
            raise RagUnavailable("문서 검색에 실패했습니다.") from None
        finally:
            self.lock.release()

    def ingest(self, directory: Path):
        from app.rag.documents import load_chunks

        chunks = load_chunks(directory, self.model.tokenizer)
        content_hash = hashlib.sha256("".join(chunk.id for chunk in chunks).encode()).hexdigest()
        name = f"manuals-{content_hash[:12]}-{uuid.uuid4().hex[:8]}"
        metadata = {"complete": False, "revision": self.revision, "dimension": 1024}
        collection = self.client.create_collection(name, embedding_function=None, metadata=metadata,
                                                   configuration={"hnsw": {"space": "cosine"}})
        for start in range(0, len(chunks), 8):
            batch = chunks[start:start + 8]
            vectors = self.model.encode([chunk.text for chunk in batch], normalize_embeddings=True).tolist()
            collection.add(ids=[chunk.id for chunk in batch], embeddings=vectors,
                           documents=[chunk.text for chunk in batch], metadatas=[chunk.metadata for chunk in batch])
        if collection.count() != len(chunks):
            raise RagUnavailable("Incomplete ingestion")
        collection.modify(metadata={**metadata, "complete": True})
        manifest = {"collection": name, "revision": self.revision, "dimension": 1024, "count": len(chunks),
                    "content_hash": content_hash, "chunk_size": 500, "overlap": 80}
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest.with_name(f".active-{uuid.uuid4().hex}.json")
        temporary.write_text(json.dumps(manifest), encoding="utf-8")
        os.replace(temporary, self.manifest)
        return manifest
