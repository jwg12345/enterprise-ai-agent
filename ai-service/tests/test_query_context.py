import json
from unittest.mock import Mock

import pytest
from app.rag.store import RagStore


@pytest.mark.parametrize("prefix", ["", "사내 IT 장애 운영 매뉴얼: "])
def test_context_only_changes_embedding_input_preserving_acl_and_distance(tmp_path, prefix):
    manifest = tmp_path / "active.json"
    manifest.write_text(json.dumps({"collection": "test", "revision": "a" * 40, "dimension": 1024, "count": 3}))
    client, model = Mock(), Mock()
    collection = client.get_collection.return_value
    collection.metadata = {"complete": True}
    collection.count.return_value = 3
    model.encode.return_value.tolist.return_value = [[0.0] * 1024]
    collection.query.return_value = {
        "ids": [["yes", "far", "private"]], "documents": [["원문", "먼 문서", "비공개"]],
        "metadatas": [[{"allowed_viewer": allowed, "document_id": "m", "version": "1", "section": "s"}
                       for allowed in [True, True, False]]], "distances": [[0.50295275, 0.5082075, 0.1]]}
    store = RagStore(model, client, "a" * 40, manifest, 0.503, prefix)
    result = store.search("문서만으로 변경할 수 있나요?", "viewer")
    model.encode.assert_called_once_with([prefix + "문서만으로 변경할 수 있나요?"], normalize_embeddings=True)
    assert [c["chunk_id"] for c in result] == ["yes"]
    assert result[0]["text"] == "원문"
    assert collection.query.call_args.kwargs["where"] == {"allowed_viewer": True}
