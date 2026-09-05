import os
import uuid
import httpx
import streamlit as st


def render_answers():
    st.divider()
    st.subheader("운영 매뉴얼 질문")
    st.caption("실제 검색 근거를 표시합니다. LLM 미연결 모드에서는 요약을 생성하지 않습니다.")
    with st.form("manual-question"):
        query = st.text_area("질문", "P1 네트워크 장애의 점검 순서를 알려줘", max_chars=4000)
        submitted = st.form_submit_button("문서 근거 찾기")
    if submitted:
        st.session_state.pop("answer_result", None)
        request_id = str(uuid.uuid4())
        try:
            with st.spinner("문서를 검색하고 있습니다…"):
                response = httpx.post(
                    os.environ.get("AI_API_URL", "http://ai:8000") + "/v1/answers",
                    json={"query": query}, headers={
                        "Authorization": "Bearer " + os.environ.get("DEMO_VIEWER_TOKEN", ""),
                        "X-Request-ID": request_id
                    }, timeout=65, trust_env=False
                )
                if response.status_code != 200:
                    st.error(f"검색·답변을 완료하지 못했습니다. 요청 ID: {request_id}")
                else:
                    st.session_state["answer_result"] = response.json()
        except (httpx.HTTPError, ValueError):
            st.error(f"검색 서비스 연결에 실패했습니다. 요청 ID: {request_id}")
    if "answer_result" in st.session_state:
        result = st.session_state["answer_result"]
        if result["mode"] == "extractive":
            st.caption("검색 원문 모드 · LLM 요약 미연결")
        else:
            st.caption("LLM 답변 · 아래 원문과 함께 확인하세요")
        st.text(result["answer"])
        for source in result["citations"]:
            with st.expander(f'{source["document_id"]} · {source["section"]} · v{source["version"]}'):
                st.text(source["text"])
                st.caption(f'cosine distance: {source["distance"]:.4f} · 확률이나 정확도가 아닙니다.')
                st.caption(f'chunk: {source["chunk_id"]}')
        st.caption("관련성 임계값은 아직 실제 검색 평가로 보정하지 않았습니다.")
        st.caption(f'요청 ID: {result["request_id"]}')
