import json
import os
from uuid import uuid4

import httpx
import streamlit as st


ERROR_MESSAGES = {
    "LLM_NOT_ENABLED": "AI 초안 생성용 LLM이 연결되지 않았습니다. LLM_MODE와 서비스 설정을 확인하세요.",
    "RAG_UNAVAILABLE": "매뉴얼 검색 서비스가 준비되지 않았습니다.",
    "DRAFT_GENERATION_FAILED": "LLM 초안 응답이나 출처 검증에 실패했습니다.",
    "DRAFT_TIMEOUT": "AI 초안 생성 시간이 초과되었습니다.",
    "INCIDENT_NOT_IN_RESULTS": "조회 범위에 해당 장애가 없습니다. 장애 목록을 다시 조회하세요.",
    "INCIDENT_RESOLVED": "이미 해결된 장애입니다. 미해결 장애를 선택하세요.",
    "UNSAFE_REQUEST": "허용되지 않은 요청입니다. 점검 초안 요청을 입력하세요.",
    "FORBIDDEN": "운영자 권한이 필요합니다.",
    "APPROVAL_EXPIRED": "승인 요청이 만료됐습니다. 실행 상태를 새로고침하세요.",
    "RUN_BUSY": "같은 실행을 처리 중입니다. 잠시 후 상태를 조회하세요.",
}


def ticket_request(method, path, payload=None, key=None):
    token = os.environ.get("DEMO_OPERATOR_TOKEN", "")
    if len(token) < 24:
        raise RuntimeError("서버의 운영자 인증 설정이 필요합니다.")
    trace = str(uuid4())
    headers = {"Authorization": "Bearer " + token, "X-Request-ID": trace}
    if key:
        headers["Idempotency-Key"] = key
    try:
        response = httpx.request(method, os.environ.get("AI_API_URL", "http://ai:8000") + path,
                                 headers=headers, json=payload, timeout=55, trust_env=False)
        if response.status_code != 200:
            message = "요청을 처리하지 못했습니다. 서비스 상태와 입력을 확인하세요."
            try:
                code = response.json()["error"]["code"]
                if isinstance(code, str):
                    message = ERROR_MESSAGES.get(code, message)
            except (ValueError, KeyError, TypeError):
                pass
            # 서버 원문 오류를 그대로 표시하지 않고 허용한 안내만 사용합니다.
            raise RuntimeError(f"{message} HTTP {response.status_code} · 요청 ID: {trace}")
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise RuntimeError(f"연결 결과가 불명확합니다. 최근 실행을 조회하세요. 요청 ID: {trace}") from None


def render_tickets():
    st.divider()
    st.header("후속 티켓 승인")
    st.caption("로컬 운영자 시연 · 초안 검토 후 사람 승인 · 실제 시스템 변경 없이 프로젝트 DB에 티켓을 저장합니다.")
    from draft_ui import render_draft_preview
    render_draft_preview(ticket_request)
    st.subheader("직접 작성한 초안")
    with st.form("ticket-draft"):
        incident = st.text_input("장애 ID", value="INC-014", max_chars=32)
        title = st.text_input("티켓 제목", value="네트워크 장애 후속 점검", max_chars=200)
        body = st.text_area("점검 요청 내용", value="관측된 장애와 운영 매뉴얼을 확인하고 점검 결과를 기록합니다.", max_chars=6000)
        team = st.text_input("담당 팀", value="Platform", max_chars=80)
        priority = st.selectbox("티켓 우선순위", ["P1", "P2", "P3"])
        submit = st.form_submit_button("초안 등록 · 승인 대기")
    if submit:
        draft = {"incident_id": incident, "title": title, "body": body, "team": team, "priority": priority}
        fingerprint = json.dumps(draft, sort_keys=True, ensure_ascii=False)
        if st.session_state.get("ticket_fingerprint") != fingerprint:
            st.session_state["ticket_fingerprint"] = fingerprint
            st.session_state["ticket_key"] = str(uuid4())
        try:
            st.session_state["ticket_run"] = ticket_request("POST", "/v1/ticket-runs", {"draft": draft}, st.session_state["ticket_key"])
        except RuntimeError as exc:
            st.error(str(exc))
    if st.button("최근 실행 불러오기"):
        try:
            st.session_state["ticket_history"] = ticket_request("GET", "/v1/ticket-runs")["items"]
        except RuntimeError as exc:
            st.error(str(exc))
    history = st.session_state.get("ticket_history", [])
    if history:
        selected = st.selectbox("이어서 확인할 실행", [item["run_id"] for item in history])
        if st.button("선택한 실행 조회"):
            try:
                st.session_state["ticket_run"] = ticket_request("GET", "/v1/ticket-runs/" + selected)
            except RuntimeError as exc:
                st.error(str(exc))
    run = st.session_state.get("ticket_run")
    if not run:
        return
    st.caption("실행 ID: " + run["run_id"])
    status = run["status"]
    labels = {"WAITING_APPROVAL": "승인 대기", "COMPLETED": "티켓 생성 완료", "REJECTED": "거절됨",
              "EXPIRED": "만료됨", "RECONCILING": "처리 결과 확인 필요", "RUNNING": "실행 준비 중"}
    st.write("상태: " + labels.get(status, status))
    approval = run.get("approval")
    if approval:
        with st.container(border=True):
            st.subheader(approval["draft"]["title"])
            st.text(approval["draft"]["body"])
            st.caption(f'{approval["draft"]["incident_id"]} · {approval["draft"]["team"]} · {approval["draft"]["priority"]}')
            st.caption("만료 시각: " + approval["expires_at"])
    action = None
    if status == "WAITING_APPROVAL":
        approve, reject = st.columns(2)
        if approve.button("승인하고 티켓 생성", type="primary"):
            action = "approve"
        if reject.button("거절"):
            action = "reject"
    if action:
        try:
            st.session_state["ticket_run"] = ticket_request("POST", f'/v1/ticket-runs/{run["run_id"]}/decisions',
                                                            {"approval_id": approval["approval_id"], "decision": action})
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))
    if status in {"RUNNING", "RECONCILING"} and st.button("저장된 실행 재개"):
        try:
            st.session_state["ticket_run"] = ticket_request("POST", f'/v1/ticket-runs/{run["run_id"]}/resume')
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))
    if st.button("실행 상태 새로고침"):
        try:
            st.session_state["ticket_run"] = ticket_request("GET", f'/v1/ticket-runs/{run["run_id"]}')
            st.rerun()
        except RuntimeError as exc:
            st.error(str(exc))
    if run.get("ticket_id"):
        st.success("생성된 티켓 ID: " + run["ticket_id"])
