#운영 매뉴얼을 읽어서 ChromaDB에 저장하는 작업 실행
import os
from pathlib import Path
from app.rag.store import RagStore

if __name__ == "__main__":
    store = RagStore.from_env(allow_download=True)
    manifest = store.ingest(Path(os.environ.get("MANUAL_DIR", "/manuals")))
    print("Ingested", manifest["count"], "chunks into", manifest["collection"])
