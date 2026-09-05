from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_query_displays_actual_api_result():
    payload = {"items": [{"id": "INC-014", "category": "NETWORK", "severity": "P1",
               "status": "OPEN", "occurred_at": "2026-08-14T00:00:00Z",
               "cause": "Gateway Timeout", "version": 1}], "total": 1, "page": 0, "size": 20}
    with patch("api_client.fetch_incidents", return_value=(payload, "trace-test")) as fetch:
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        app.button[0].click().run()
        assert not app.exception
        assert app.metric[0].value == "1건"
        assert app.dataframe[0].value.iloc[0]["장애 ID"] == "INC-014"
        assert fetch.call_args.args[0]["to"] == "2026-09-01T00:00:00+09:00"
