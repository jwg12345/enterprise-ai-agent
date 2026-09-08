import os
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from api_client import QueryError, fetch_incidents

st.set_page_config(page_title="기업 업무 대응 AI Agent", page_icon="📋", layout="wide")
m2_enabled = os.environ.get("M2_ENABLED", "false").lower() == "true"
m3_enabled = os.environ.get("M3_ENABLED", "false").lower() == "true"
st.caption("ENTERPRISE AI AGENT  /  " + ("M3" if m3_enabled else "M2" if m2_enabled else "M1"))
st.title("장애 기록을 한곳에서 확인하세요")
st.write("기간과 조건을 선택하면 업무 시스템에 저장된 장애를 조회합니다.")
st.info("문서 검색과 운영자용 후속 티켓 승인 시연을 제공합니다." if m3_enabled else
        "문서 근거 검색을 연결했습니다. 티켓 생성·승인 기능은 아직 지원하지 않습니다." if m2_enabled
        else "현재는 장애 조회 단계입니다. AI 답변·문서 검색·승인 기능은 다음 단계에서 연결됩니다.")

with st.form("incident-search"):
    a, b, c, d = st.columns([2, 2, 1, 1])
    start = a.date_input("시작일", date(2026, 8, 1))
    end = b.date_input("종료일 (포함)", date(2026, 8, 31))
    severity = c.selectbox("등급", ["전체", "P1", "P2", "P3"], index=1)
    category = d.selectbox("분류", ["전체", "NETWORK", "SERVER", "APPLICATION"], index=1)
    e, f, g = st.columns([2, 1, 1])
    status = e.selectbox("상태", ["전체", "OPEN", "IN_PROGRESS", "RESOLVED"])
    page = f.number_input("페이지", min_value=1, max_value=100001, value=1)
    size = g.selectbox("페이지당 건수", [10, 20, 50], index=1)
    submitted = st.form_submit_button("장애 조회", type="primary", width="stretch")

if submitted:
    st.session_state.pop("result", None)
    if end < start or (end - start).days >= 366:
        st.error("조회 기간은 1일 이상 366일 이하로 선택해 주세요.")
    else:
        tz = timezone(timedelta(hours=9))
        params = {
            "from": datetime.combine(start, time.min, tz).isoformat(),
            "to": datetime.combine(end + timedelta(days=1), time.min, tz).isoformat(),
            "page": int(page) - 1, "size": size
        }
        for name, value in [("severity", severity), ("category", category), ("status", status)]:
            if value != "전체":
                params[name] = value
        try:
            with st.spinner("업무 시스템에서 조회하고 있습니다…"):
                result, request_id = fetch_incidents(params)
            st.session_state["result"] = result, request_id, start, end
            st.session_state["incident_params"] = params
        except QueryError as exc:
            st.error(str(exc))

if "result" in st.session_state:
    result, request_id, start, end = st.session_state["result"]
    total, current = st.columns(2)
    total.metric("전체 조회 결과", f'{result["total"]}건')
    current.metric("현재 페이지", f'{result["page"] + 1}페이지')
    st.caption(f"조회 기간: {start} ~ {end} · Asia/Seoul · 합성 시연 데이터")
    if result["items"]:
        frame = pd.DataFrame(result["items"])
        frame["occurred_at"] = pd.to_datetime(frame["occurred_at"], utc=True).dt.tz_convert("Asia/Seoul")
        frame = frame.rename(columns={"id": "장애 ID", "category": "분류", "severity": "등급",
                         "status": "상태", "occurred_at": "발생 시각", "cause": "관측된 원인",
                         "version": "버전"})
        st.dataframe(frame, hide_index=True, width="stretch")
    else:
        st.success("선택한 조건에 해당하는 장애가 없습니다.")
    st.caption(f"요청 ID: {request_id}")
else:
    st.caption("시연 예시: 2026년 8월 · P1 · NETWORK → 미해결 1건, 해결 완료 1건")

if m2_enabled:
    from answers_ui import render_answers
    render_answers()

if m3_enabled:
    from tickets_ui import render_tickets
    render_tickets()
