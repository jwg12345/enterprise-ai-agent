import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class RagUnavailable(Exception):
    pass

#처리 단계별 시간 측정(RAG 검색의 각 단계가 얼마나 걸렸는지 측정) -> 아래 search()함수에서 사용
# 임베딩 41.6초 벡터 검색 0.184초 병목 구분
@contextmanager
def measured_phase(operation_id, phase):
    logger = logging.getLogger("enterprise.ai")
    base = {"event": "rag_phase", "operation_id": operation_id, "phase": phase}
    started = time.monotonic()
    logger.info(json.dumps({**base, "state": "started"}))
    state = "completed"
    try:
        yield
    except BaseException:
        state = "failed"
        raise
    finally:
        logger.info(json.dumps({**base, "state": state, "duration_ms": round((time.monotonic()-started)*1000)}))


class RagStore:
    #RAG 객체 초기화
    # model	BGE-M3 임베딩 모델
    # client	ChromaDB 접속 클라이언트
    # revision	사용 중인 모델의 고정 버전
    # manifest	활성 인덱스 정보를 담은 JSON 파일 경로
    # max_distance	검색 결과를 허용할 최대 코사인 거리
    # query_prefix	임베딩 전에 질문 앞에 붙일 문자열
    # lock	동시 검색 실행을 제한하는 잠금 장치
    def __init__(self, model, client, revision: str, manifest: Path, max_distance: float, query_prefix: str = ""):
        self.model, self.client, self.revision = model, client, revision
        self.manifest, self.max_distance = manifest, max_distance
        self.query_prefix = query_prefix
        self.lock = threading.Lock() # 동시에 여러 검색이 들어왔을 때 임베딩 연산이 겸치지 않도록 하기 위함.

    #임베딩 모델과 DB 연결 준비
    @classmethod
    def from_env(cls, allow_download=False): #환경변수를 읽어 RAG 검색에 필요한 객체를 구성
        revision = os.environ.get("EMBEDDING_REVISION", "")
        if not re.fullmatch(r"[a-f0-9]{40}", revision): # 고정된 revision을 사용하면 모델 업데이트로 인해 검색 환경이 예상치 못하게 바뀌는 문제를 줄일 수 있습니다.
            raise RagUnavailable("BGE-M3의 고정 commit revision이 필요합니다.")
        # 선택적 의존성을 기본 M1 기동 시 import하지 않습니다.
        import chromadb
        from chromadb.config import Settings
        from sentence_transformers import SentenceTransformer
        #BGE-M3 모델 로딩
        model = SentenceTransformer("BAAI/bge-m3", revision=revision, device="cpu",
                                    cache_folder=os.environ.get("HF_HOME", "/model-cache"),
                                    local_files_only=not allow_download, trust_remote_code=False)
        model.max_seq_length = 1024 # 모델에 전달하는 텍스트의 최대 토큰 길이를 1,024로 설정합니다. 일반적인 추론에서는 이를 초과하는 입력이 잘릴 수 있습니다.
        if model.get_sentence_embedding_dimension() != 1024:
            raise RagUnavailable("Unexpected embedding dimension")

        #ChromaDB 연결
        client = chromadb.HttpClient(host=os.environ.get("CHROMA_HOST", "chroma"),
                                     port=int(os.environ.get("CHROMA_PORT", "8000")),
                                     settings=Settings(anonymized_telemetry=False))

        #환경변수가 없다면 코사인 거리 임계값을 0.45로 설정
        #ex) 거리 검색 0.30인 문서는 통과할 수 있지만 0.60인 문서는 제외 
        threshold = float(os.environ.get("RAG_MAX_DISTANCE", "0.45"))
        if not 0 <= threshold <= 2:
            raise RagUnavailable("Invalid cosine distance threshold")
        return cls(model, client, revision, Path(os.environ.get("INDEX_MANIFEST", "/index/active.json")), threshold,
                   os.environ.get("RAG_QUERY_PREFIX", ""))
    #현재 활성 인덱스 확인
    def active(self):
        try:
            manifest = json.loads(self.manifest.read_text(encoding="utf-8")) #manifest는 현재 검색에 사용해야 하는 ChromaDB 컬렉션의 정보를 기록한 파일
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
            
    #RAG 서비스 상태 확인
    def ready(self):
        try:
            self.client.heartbeat()
            self.active()
            return True
        except Exception:
            return False

    #실제 질문을 검색->문서를 찾는 기능
    def search(self, query: str, role: str): #query:사용자가 입력한 질문 / role:사용자의 권한
        if role not in {"viewer", "operator"}: #viewer 또는 operator 권한만 허용
            raise RagUnavailable("Unsupported role")
        # timeout 후에도 살아 있는 embedding thread가 자원을 중복 점유하지 않게 합니다.
        if not self.lock.acquire(blocking=False): #동시 검색 방지 -> 이미 다른 스레드에서 검색 중이라면 새 검색을 즉시 거절
            raise RagUnavailable("검색 작업 중입니다. 잠시 후 다시 시도하세요.")
        try: 
            operation_id = str(uuid.uuid4())

            #새 작업 ID를 만들고 인덱스 확인
            with measured_phase(operation_id, "index_check"): #활성 인덱스 확인
                collection, manifest = self.active() 
            #질문을 임베딩 벡터로 변환
            with measured_phase(operation_id, "embedding"): #BGE-M3 질문 임베딩 -> 질문을 입력받아 1,024차원 벡터로 변환
                vector = self.model.encode([self.query_prefix + query], normalize_embeddings=True).tolist()
            #ChromaDB에서 유사 문서 검색
            with measured_phase(operation_id, "vector_search"): #ChromaDB 벡터 검색
                found = collection.query(query_embeddings=vector, n_results=min(5, manifest["count"]),
                                         where={f"allowed_{role}": True}, # 예를 들어 role="viewer"이면 다음처럼 바뀝니다. -> where={"allowed_viewer": True}
                                         include=["documents", "metadatas", "distances"])
            
            #검색 결과 추가 필터링
            citations = []
            for cid, text, metadata, distance in zip(
                found["ids"][0], found["documents"][0], found["metadatas"][0], found["distances"][0], strict=True
            ):
                if distance <= self.max_distance and metadata.get(f"allowed_{role}") is True:
                    citations.append({"chunk_id": cid, "text": text, "distance": distance,
                                      "document_id": metadata["document_id"], "version": metadata["version"],
                                      "section": metadata["section"], "index_version": manifest["collection"]})
            return citations

        #예외 및 잠금 해제
        except RagUnavailable:
            raise
        except Exception:
            raise RagUnavailable("문서 검색에 실패했습니다.") from None
        finally:
            self.lock.release()

    #운영 매뉴얼을 ChromaDB에 저장->문서(운영 매뉴얼)을 검색할 수 있도록 사전에 등록하는 기능
    def ingest(self, directory: Path):
        from app.rag.documents import load_chunks

        chunks = load_chunks(directory, self.model.tokenizer) #load_chunks()를 호출해 지정한 디렉터리의 문서를 청크 단위로 불러움

        #새로운 컬렉션 이름 생성 -> 청크 ID들을 연결해 SHA-256 해시를 계산 -> 이 해시 일부와 UUID를 조합해 새로운 컬렉션 이름을 만듦
        content_hash = hashlib.sha256("".join(chunk.id for chunk in chunks).encode()).hexdigest()
        name = f"manuals-{content_hash[:12]}-{uuid.uuid4().hex[:8]}"

        #새 ChromaDB 컬렉션 생성 / complete=False는 아직 인덱스 구축이 끝나지 않았다는 의미 / space="cosine"은 코사인 거리 기반으로 검색하도록 설정
        metadata = {"complete": False, "revision": self.revision, "dimension": 1024}
        collection = self.client.create_collection(name, embedding_function=None, metadata=metadata,
                                                   configuration={"hnsw": {"space": "cosine"}})

        #문서 청크를 8개씩 임베딩
        for start in range(0, len(chunks), 8):
            batch = chunks[start:start + 8]
            vectors = self.model.encode([chunk.text for chunk in batch], normalize_embeddings=True).tolist()
            #이어서 ChromaDB에 저장 (ids:각 청크의 고유 ID, embeddings:BGE-M3가 생성한 벡터, documents:청크의 원문, metadatas:문서ID, 버전, 권한 등의 부가 정보)
            collection.add(ids=[chunk.id for chunk in batch], embeddings=vectors,
                           documents=[chunk.text for chunk in batch], metadatas=[chunk.metadata for chunk in batch])
        #인덱스 구축 완료 확인 
        if collection.count() != len(chunks):
            raise RagUnavailable("Incomplete ingestion")
        collection.modify(metadata={**metadata, "complete": True})
        #활성 인덱스 교체 -> 현재 컬렉션의 정보를 manifest로 구성 
        manifest = {"collection": name, "revision": self.revision, "dimension": 1024, "count": len(chunks),
                    "content_hash": content_hash, "chunk_size": 500, "overlap": 80}
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        #임시 파일에 기록 
        temporary = self.manifest.with_name(f".active-{uuid.uuid4().hex}.json")
        temporary.write_text(json.dumps(manifest), encoding="utf-8")
        os.replace(temporary, self.manifest) # 새 인덱스가 완성되기 전에는 기존 활성 인덱스를 그대로 유지하고, 새 인덱스 구축이 끝난 뒤 활성 인덱스를 가리키는 파일을 교체합니다.
        return manifest
