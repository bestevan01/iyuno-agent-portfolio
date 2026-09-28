"""Streamlit 데모.

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from agent import load_agent  # noqa: E402
from agent.feedback import log_run, record_feedback  # noqa: E402

st.set_page_config(page_title="OWASP 보안 Q&A 에이전트", page_icon="🛡️", layout="wide")


@st.cache_resource(show_spinner="인덱스 로딩 중…")
def get_agent():
    return load_agent()


agent = get_agent()
mode = f"LLM · {agent.s.llm_model}" if agent.client else "오프라인(규칙 라우터 + 발췌)"

st.title("🛡️ OWASP 보안 Q&A 에이전트")
st.caption(f"RAG + tool calling · 문서 {len({c.doc_id for c in agent.index.chunks})}개 / "
           f"조각 {len(agent.index.chunks)}개 · 모드: {mode} · 검색: {agent.index.mode}")

EXAMPLES = [
    "SSRF를 막으려면 어떻게 해야 하나요?",
    "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N 는 몇 점인가요?",
    "CWE-89는 어느 Top 10 카테고리인가요?",
    '비밀번호 "qwerty123" 괜찮은가요? MFA는 안 써요.',
]
cols = st.columns(len(EXAMPLES))
for c, ex in zip(cols, EXAMPLES, strict=True):
    if c.button(ex, use_container_width=True):
        st.session_state["q"] = ex

q = st.text_input("질문", key="q", placeholder="예: 비밀번호는 어떤 해시 알고리즘으로 저장해야 하나요?")
if st.button("질문하기", type="primary") and q.strip():
    st.session_state["res"] = agent.ask(q)
    log_run(st.session_state["res"], agent.s.db_file)

res = st.session_state.get("res")
if res:
    left, right = st.columns([3, 2])
    with left:
        st.subheader("답변")
        st.markdown(res.answer)
        if res.citations:
            st.markdown("**출처**")
            for c in res.citations:
                st.markdown(f"[{c.ref}] [{c.title} — {c.section}]({c.url})")
        st.divider()
        st.markdown("**이 답변이 도움이 됐나요?** (피드백은 평가셋 후보로 저장됩니다)")
        corr = st.text_input("틀렸다면 올바른 내용을 적어주세요", key="corr")
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("👍 좋아요"):
            record_feedback(res.question, res.answer, 1, "", [c.chunk_id for c in res.citations], agent.s.db_file)
            st.success("저장했습니다.")
        if b2.button("👎 아쉬워요"):
            record_feedback(res.question, res.answer, -1, corr, [c.chunk_id for c in res.citations], agent.s.db_file)
            st.success("저장했습니다. 수정 의견은 다음 평가 라운드에 반영됩니다.")
    with right:
        st.subheader("에이전트 실행 기록")
        m1, m2, m3 = st.columns(3)
        m1.metric("지연시간", f"{res.latency_ms:.0f} ms")
        m2.metric("토큰", f"{res.prompt_tokens + res.completion_tokens:,}")
        m3.metric("비용", f"${res.cost_usd:.4f}")
        for i, t in enumerate(res.tool_calls, 1):
            with st.expander(f"{i}. {t.name}  ·  {t.latency_ms:.0f} ms", expanded=i == 1):
                st.json({"arguments": t.arguments, "output": t.output})
