"""
Code Preview Panel — Streamlit component for the Coder Agent.

Shows real-time:
- Code the agent is reading/writing (syntax highlighted)
- Which files were changed
- PR link when submitted
- Senior Coder feedback inline (red highlights on rejection, green tick on approval)

Run with: streamlit run frontend/components/CodePreview.py
"""

import asyncio
import json
import threading
from datetime import datetime

import streamlit as st

from agents.coder.agent import CoderAgent, on_agent_event

# ── Page config ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="NexusSynapse — Coder Agent",
    page_icon="🔧",
    layout="wide",
)

# ── Session state ────────────────────────────────────────────────────

if "events" not in st.session_state:
    st.session_state.events = []
if "running" not in st.session_state:
    st.session_state.running = False
if "result" not in st.session_state:
    st.session_state.result = None
if "files" not in st.session_state:
    st.session_state.files = {}  # path → content
if "pr_url" not in st.session_state:
    st.session_state.pr_url = None
if "feedback" not in st.session_state:
    st.session_state.feedback = None  # Senior Coder feedback
if "approved" not in st.session_state:
    st.session_state.approved = False


def event_handler(event: dict):
    """Callback that receives events from the Coder Agent."""
    st.session_state.events.append(event)

    if event["type"] == "file_changed":
        st.session_state.files[event["path"]] = event["content"]
    elif event["type"] == "pr_created":
        st.session_state.pr_url = event["url"]
    elif event["type"] == "rejection":
        st.session_state.feedback = {
            "status": "rejected",
            "text": event["feedback"],
            "score": event["score"],
        }
        st.session_state.approved = False
    elif event["type"] == "agent_complete":
        st.session_state.running = False
        if event.get("status") == "complete":
            st.session_state.approved = True


# ── Header ───────────────────────────────────────────────────────────

st.title("🔧 NexusSynapse — Coder Agent")
st.caption("Autonomous code generation powered by Azure AI Foundry + GitHub MCP")

# ── Task input ───────────────────────────────────────────────────────

col_input, col_status = st.columns([3, 1])

with col_input:
    task = st.text_area(
        "Task from Manager Agent",
        placeholder="e.g. Fix the authentication bug in the login API — users get 401 even with valid tokens",
        height=100,
    )

with col_status:
    if st.session_state.running:
        st.info("⏳ Agent is working...")
    elif st.session_state.approved:
        st.success("✅ Code approved!")
    elif st.session_state.feedback:
        st.error(f"❌ Rejected — {st.session_state.feedback['score']}/100")
    else:
        st.empty()

if st.button("🚀 Run Coder Agent", disabled=st.session_state.running, type="primary"):
    if not task.strip():
        st.warning("Enter a task first.")
    else:
        st.session_state.running = True
        st.session_state.events = []
        st.session_state.files = {}
        st.session_state.pr_url = None
        st.session_state.feedback = None
        st.session_state.approved = False

        on_agent_event(event_handler)

        def run_agent():
            agent = CoderAgent()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(agent.run(task))
            st.session_state.result = result
            st.session_state.running = False

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()
        st.rerun()

# ── Rejection feedback (if Senior Coder rejected) ──────────────────

if st.session_state.feedback and st.session_state.feedback["status"] == "rejected":
    with st.expander("❌ Senior Coder Feedback", expanded=True):
        st.error(f"**Score: {st.session_state.feedback['score']}/100**")
        st.markdown(st.session_state.feedback["text"])

        if st.button("🔄 Fix & Resubmit"):
            st.session_state.running = True

            def resubmit():
                agent = CoderAgent()
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    agent.handle_rejection(
                        st.session_state.feedback["text"],
                        st.session_state.feedback["score"],
                    )
                )
                st.session_state.result = result

            thread = threading.Thread(target=resubmit, daemon=True)
            thread.start()
            st.rerun()

# ── Code preview panel ───────────────────────────────────────────────

st.divider()
st.subheader("📝 Code Changes")

if st.session_state.files:
    tabs = st.tabs(list(st.session_state.files.keys()))
    for tab, (path, content) in zip(tabs, st.session_state.files.items()):
        with tab:
            ext = path.rsplit(".", 1)[-1] if "." in path else "text"
            lang_map = {
                "py": "python", "js": "javascript", "ts": "typescript",
                "yml": "yaml", "yaml": "yaml", "json": "json",
                "html": "html", "css": "css", "sh": "bash",
            }
            lang = lang_map.get(ext, ext)

            # If rejected, show with a red border
            if st.session_state.feedback and not st.session_state.approved:
                st.markdown(
                    f'<div style="border-left: 4px solid #ff4b4b; padding-left: 12px;">'
                    f'<small style="color: #ff4b4b;">⚠️ Needs revision</small></div>',
                    unsafe_allow_html=True,
                )

            st.code(content, language=lang, line_numbers=True)

            # Green tick if approved
            if st.session_state.approved:
                st.success(f"✅ {path} — Approved by Senior Coder")
else:
    st.caption("No files changed yet. Run the agent to see code here.")

# ── PR link ──────────────────────────────────────────────────────────

if st.session_state.pr_url:
    st.divider()
    st.subheader("🔗 Pull Request")
    st.markdown(f"**PR Created:** [{st.session_state.pr_url}]({st.session_state.pr_url})")

# ── Agent event log ──────────────────────────────────────────────────

st.divider()
with st.expander("📋 Agent Activity Log", expanded=False):
    for event in reversed(st.session_state.events):
        ts = event.get("timestamp", "")[:19]
        etype = event["type"]

        if etype == "tool_call":
            st.markdown(f"`{ts}` **→ {event['tool']}**")
        elif etype == "agent_message":
            st.markdown(f"`{ts}` 💬 Agent responded")
        elif etype == "file_changed":
            st.markdown(f"`{ts}` 📝 Changed: `{event['path']}`")
        elif etype == "pr_created":
            st.markdown(f"`{ts}` 🔗 PR: {event['url']}")
        elif etype == "rejection":
            st.markdown(f"`{ts}` ❌ Rejected (score: {event['score']}/100)")
        elif etype == "agent_complete":
            st.markdown(f"`{ts}` ✅ Agent complete")
        else:
            st.markdown(f"`{ts}` {etype}")

# ── Result summary ───────────────────────────────────────────────────

if st.session_state.result:
    st.divider()
    st.subheader("📊 Summary")
    r = st.session_state.result
    col1, col2, col3 = st.columns(3)
    col1.metric("Status", r.get("status", "—"))
    col2.metric("Files Changed", len(r.get("files_changed", [])))
    col3.metric("Attempt", r.get("attempt", 1))
