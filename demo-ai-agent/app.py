"""AI SRE Agent — demo UI (Streamlit).

An interactive interface where an on-call engineer asks about a
production incident in plain English; the agent autonomously queries the live
AWS RDS `orders` database and returns a root-cause diagnosis -- and the right-
hand panel makes the Teleport story visible: the agent's short-lived identity,
its least-privilege scope, a live "try an admin action -> DENIED" button, and
an audit summary of exactly what it ran.

Run:  USE the helper -> ./run_ui.sh   (or)
      .venv/bin/streamlit run app.py
Requires the Teleport tunnel running (tbot) for the secure path.
"""

import os
import time
from datetime import datetime, timezone

import psycopg2
import streamlit as st
from cryptography import x509

from agent_core import iter_agent_events

HERE = os.path.dirname(os.path.abspath(__file__))
TBOT_CERT = os.path.join(HERE, "teleport", "tbot-data", "tlscert")
TENANT_URL = "https://your-tenant.teleport.sh"
SECURE_PORT = 5433      # tbot tunnel as readonly_agent (allowed)
PRIV_PORT = 5434        # tbot tunnel as postgres super-user (denied by policy)

st.set_page_config(page_title="AI SRE Agent · secured by Teleport",
                   page_icon="🤖", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem;}
  .tp-badge {background:#512fc9; color:#fff; padding:3px 10px; border-radius:6px;
             font-size:0.72rem; font-weight:600; letter-spacing:.3px;}
  .tp-card {border:1px solid #e6e6ef; border-radius:10px; padding:14px 16px; margin-bottom:12px;}
  .tp-ok {color:#0a7d33; font-weight:600;}
  .tp-bad {color:#c81e1e; font-weight:600;}
  .tp-muted {color:#6b7280; font-size:0.85rem;}
  .stCodeBlock {font-size:0.82rem;}
</style>
""", unsafe_allow_html=True)


# ---------- Teleport helpers ---------------------------------------------------
def identity_info():
    """Read the bot's short-lived cert: expiry + how long ago tbot last renewed."""
    if not os.path.exists(TBOT_CERT):
        return None
    try:
        cert = x509.load_pem_x509_certificate(open(TBOT_CERT, "rb").read())
        expires = cert.not_valid_after_utc
        renewed_age = time.time() - os.path.getmtime(TBOT_CERT)
        secs_left = (expires - datetime.now(timezone.utc)).total_seconds()
        return {"expires": expires, "secs_left": secs_left, "renewed_age": renewed_age}
    except Exception:
        return None


def try_action(port, user):
    """Attempt a DB connection through a given tunnel; return (ok, message)."""
    try:
        c = psycopg2.connect(host="127.0.0.1", port=str(port), dbname="opsdb",
                             user=user, sslmode="disable", connect_timeout=15)
        cur = c.cursor(); cur.execute("select current_user"); who = cur.fetchone()[0]
        c.close()
        return True, f"Connected as {who}"
    except Exception as e:
        return False, str(e).strip().splitlines()[0]


def tunnel_up():
    ok, _ = try_action(SECURE_PORT, "readonly_agent")
    return ok


# ---------- session state ------------------------------------------------------
if "history" not in st.session_state:
    st.session_state.history = []          # list of {"role","blocks"}
if "secure" not in st.session_state:
    st.session_state.secure = True
if "priv_result" not in st.session_state:
    st.session_state.priv_result = None


def render_blocks(blocks):
    for kind, payload in blocks:
        if kind == "md":
            st.markdown(payload)
        elif kind == "caption":
            st.caption(payload)
        elif kind == "sql":
            st.code(payload, language="sql")
        elif kind == "table":
            st.dataframe(payload, use_container_width=True, hide_index=True)


# ---------- layout -------------------------------------------------------------
left, right = st.columns([2, 1], gap="large")

with left:
    c1, c2 = st.columns([3, 1])
    c1.title("🤖 AI SRE Agent")
    c2.markdown("<div style='text-align:right;padding-top:18px'>"
                "<span class='tp-badge'>Secured by Teleport</span></div>",
                unsafe_allow_html=True)
    st.caption("Ask about a production incident. The agent writes its own SQL against "
               "**AWS RDS PostgreSQL** (`opsdb`, ap-south-1) and finds the root cause.")

with right:
    @st.fragment(run_every=2)
    def teleport_panel():
        st.markdown("### 🛡️ Teleport")
        secure = st.session_state.secure
        if secure:
            info = identity_info()
            st.markdown("<div class='tp-card'>"
                        "<b>Identity</b><br>"
                        "<code>agent-bot</code> &nbsp;→&nbsp; db user <code>readonly_agent</code><br>"
                        "<span class='tp-muted'>a machine identity, not the master user</span>"
                        "</div>", unsafe_allow_html=True)
            if info:
                m1, m2 = st.columns(2)
                m1.metric("Cert expires in", f"{int(info['secs_left'])}s")
                m2.metric("Renewed", f"{int(info['renewed_age'])}s ago")
                st.caption("↻ tbot auto-renews this short-lived certificate — no static password.")
            else:
                st.warning("tbot identity not found — is the tunnel running?")
            st.markdown("<div class='tp-card'>"
                        "<b>Access policy</b><br>"
                        "<span class='tp-ok'>✅ read-only</span><br>"
                        "<span class='tp-ok'>✅ database <code>opsdb</code> only</span><br>"
                        "<span class='tp-muted'>role: agent-db-readonly</span>"
                        "</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='tp-card' style='border-color:#f0c0c0;background:#fff6f6'>"
                        "<b class='tp-bad'>⚠️ Static master password</b><br>"
                        "<span class='tp-muted'>never expires · shared · over-privileged · "
                        "the DB just sees 'postgres' · no per-agent audit</span>"
                        "</div>", unsafe_allow_html=True)

        st.toggle("Route through Teleport identity", key="secure")

        # Denial demo
        if st.button("🔓 Try an admin action (connect as super-user)",
                     use_container_width=True, disabled=not st.session_state.secure):
            with st.spinner("Attempting privileged connection…"):
                ok, msg = try_action(PRIV_PORT, "postgres")
            st.session_state.priv_result = (ok, msg)
        if st.session_state.priv_result:
            ok, msg = st.session_state.priv_result
            if ok:
                st.error(f"UNEXPECTEDLY ALLOWED: {msg}")
            else:
                st.markdown(f"<div class='tp-card' style='border-color:#f0c0c0;background:#fff6f6'>"
                            f"<b class='tp-bad'>❌ DENIED by Teleport</b><br>"
                            f"<span class='tp-muted'>{msg}</span></div>", unsafe_allow_html=True)

        # Audit summary (queries from the most recent investigation)
        last = next((t for t in reversed(st.session_state.history)
                     if t["role"] == "assistant"), None)
        n_q = sum(1 for k, _ in (last["blocks"] if last else []) if k == "sql")
        st.markdown(f"### 📜 Audit\n**{n_q}** queries this investigation — each logged under "
                    f"`agent-bot`'s identity.")
        st.link_button("Open Teleport audit log ↗", f"{TENANT_URL}/web/audit/events",
                       use_container_width=True)

    teleport_panel()


# ---------- chat ---------------------------------------------------------------
with left:
    for turn in st.session_state.history:
        with st.chat_message(turn["role"]):
            render_blocks(turn["blocks"])

    prompt = st.chat_input("e.g. Checkout has felt slow in the last hour — investigate.")
    if prompt:
        secure = st.session_state.secure
        st.session_state.history.append({"role": "user", "blocks": [("md", prompt)]})
        with st.chat_message("user"):
            st.markdown(prompt)

        if secure and not tunnel_up():
            with st.chat_message("assistant"):
                st.error("Teleport tunnel isn't reachable on :5433. Start it with "
                         "`tbot start -c ./teleport/tbot.yaml`, or flip off "
                         "'Route through Teleport identity'.")
            st.stop()

        with st.chat_message("assistant"):
            blocks = []
            for ev in iter_agent_events(prompt, use_teleport=secure):
                t = ev["type"]
                if t == "connected":
                    cap = "🔌 Connected to MCP server · tools: " + ", ".join(ev["tools"])
                    st.caption(cap); blocks.append(("caption", cap))
                elif t == "text":
                    st.markdown(ev["text"]); blocks.append(("md", ev["text"]))
                elif t == "tool_call":
                    st.markdown("🔧 **Agent wrote a query:**")
                    st.code(ev["sql"], language="sql")
                    blocks.append(("md", "🔧 **Agent wrote a query:**"))
                    blocks.append(("sql", ev["sql"]))
                elif t == "tool_result":
                    if ev["status"] == "error":
                        st.error(ev["text"]); blocks.append(("md", f"⚠️ {ev['text']}"))
                    elif ev["rows"]:
                        preview = ev["rows"][:20]
                        st.dataframe(preview, use_container_width=True, hide_index=True)
                        cap = f"→ {len(ev['rows'])} row(s)"
                        st.caption(cap)
                        blocks.append(("table", preview)); blocks.append(("caption", cap))
                elif t == "error":
                    st.error(ev["text"]); blocks.append(("md", f"⚠️ {ev['text']}"))
                elif t == "final":
                    break

            st.session_state.history.append({"role": "assistant", "blocks": blocks})
        st.rerun()
