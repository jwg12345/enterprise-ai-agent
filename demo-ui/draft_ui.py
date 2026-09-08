from uuid import uuid4

import streamlit as st


def render_draft_preview(request):
    st.subheader("자연어로 초안 만들기")
    result = st.session_state.get("result")
    filters = st.session_state.get("incident_params")
    rows = [r for r in result[0]["items"] if r["status"] != "RESOLVED"] if result and filters else []
    if not rows:
        st.caption("위에서 장애를 조회한 뒤 미해결 장애를 선택하세요. 기간과 장애 선택은 직접 지정합니다.")
    else:
        with st.form("natural-ticket-preview"):
            selected = st.selectbox("초안을 만들 장애", [r["id"] for r in rows])
            query = st.text_area("어떤 후속 점검이 필요한가요?", value="운영 매뉴얼을 근거로 후속 점검 티켓 초안을 만들어줘.", max_chars=4000)
            submitted = st.form_submit_button("AI 초안 미리보기")
        if submitted:
            st.session_state.pop("natural_preview", None)
            try:
                with st.spinner("장애 상태와 매뉴얼을 확인해 초안을 작성하고 있습니다…"):
                    preview = request("POST", "/v1/ticket-draft-previews",
                                      {"query": query, "incident_id": selected, "incident_filters": filters})
                st.session_state["natural_preview"] = preview
                st.session_state["natural_preview_key"] = str(uuid4())
            except RuntimeError as exc:
                st.error(f"초안은 등록되지 않았습니다. {exc}")
    preview = st.session_state.get("natural_preview")
    if not preview:
        return
    if preview["abstain"]:
        st.info("관련 근거가 부족해 초안 생성을 보류했습니다.")
        return
    draft = preview["draft"]
    with st.container(border=True):
        st.caption("AI 생성 미리보기 · 아직 승인 요청이나 티켓이 등록되지 않았습니다.")
        st.subheader(draft["title"])
        st.text(draft["body"])
        st.caption(f'{draft["incident_id"]} · {draft["team"]} · {draft["priority"]}')
        for citation in preview["citations"]:
            with st.expander(f'{citation["document_id"]} · {citation["section"]} · {citation["version"]}'):
                st.text(citation["text"])
                st.caption("chunk: " + citation["chunk_id"])
        st.caption("장애 조회 시각: " + preview["observed_at"])
        if st.button("이 초안으로 승인 요청"):
            try:
                st.session_state["ticket_run"] = request("POST", "/v1/ticket-runs", {"draft": draft},
                                                        st.session_state["natural_preview_key"])
                st.session_state.pop("natural_preview", None)
                st.rerun()
            except RuntimeError as exc:
                st.error(str(exc))
