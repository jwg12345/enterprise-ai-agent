from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest


def test_manual_evidence_ui_is_labelled(monkeypatch):
    monkeypatch.setenv("M2_ENABLED", "true")
    response = Mock(status_code=200)
    response.json.return_value = {
        "answer": "검색 원문을 확인하세요.", "mode": "extractive", "request_id": "m2-test",
        "citations": [{"document_id": "network", "section": "점검", "version": "1",
                       "text": "Gateway를 확인합니다.", "distance": 0.2, "chunk_id": "chunk1"}]
    }
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    with patch("answers_ui.httpx.post", return_value=response):
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        next(button for button in app.button if button.label == "문서 근거 찾기").click().run()
        assert not app.exception
        assert any("LLM 요약 미연결" in caption.value for caption in app.caption)
        assert any(item.value == "Gateway를 확인합니다." for item in app.text)
