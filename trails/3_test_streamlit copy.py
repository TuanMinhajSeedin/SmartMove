import uuid

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from smartmove_hitl import build_app, detect_language, _t


def _ensure_app():
    if "app" not in st.session_state:
        st.session_state.app = build_app()
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"st-{uuid.uuid4().hex}"
    if "history" not in st.session_state:
        st.session_state.history = []  # list[tuple[role, content]]
    if "pending_interrupt" not in st.session_state:
        st.session_state.pending_interrupt = None
    if "lang" not in st.session_state:
        st.session_state.lang = "en"
    if "last_state" not in st.session_state:
        st.session_state.last_state = None


def _render_chat():
    for role, content in st.session_state.history:
        with st.chat_message(role):
            st.markdown(content)


def _append(role: str, content: str):
    st.session_state.history.append((role, content))


def _invoke_initial(user_text: str):
    cfg = {"configurable": {"thread_id": st.session_state.thread_id}}
    st.session_state.lang = detect_language(user_text)

    state = {
        "messages": [HumanMessage(content=user_text)],
        "user_query": user_text,
        "user_query_original": user_text,
        "language": None,
        "intent": None,
        "origin": None,
        "destination": None,
        "departure_time": None,
        "date": None,
        "transport_type": None,
        "fare": None,
        "missing_fields": None,
        "cypher_query": None,
        "result": None,
        "response": None,
        "follow_up_question": None,
    }

    out = st.session_state.app.invoke(state, cfg)
    return out


def _resume_with_updates(updates: dict[str, str]):
    cfg = {"configurable": {"thread_id": st.session_state.thread_id}}
    out = st.session_state.app.invoke(Command(resume=updates), cfg)
    return out


def _maybe_handle_interrupt(out: dict):
    if "__interrupt__" not in out:
        st.session_state.pending_interrupt = None
        return None

    payload = out["__interrupt__"][0].value
    st.session_state.pending_interrupt = payload
    return payload


def main():
    st.set_page_config(page_title="SmartMove (LangGraph HITL)", page_icon="🧭", layout="centered")
    _ensure_app()

    lang = st.session_state.lang
    st.title("SmartMove")
    st.caption("LangGraph Human-in-the-loop demo (interrupt + resume)")

    with st.expander("State (latest)", expanded=False):
        st.json(st.session_state.last_state or {})

    _render_chat()

    # If we are waiting for follow-up fields, show a small form.
    pending = st.session_state.pending_interrupt
    if pending:
        lang = st.session_state.lang
        question = pending.get("question") or ""
        missing_fields = list(pending.get("missing_fields") or [])

        with st.chat_message("assistant"):
            st.markdown(question)

        with st.form("follow_up_form", clear_on_submit=False):
            label_map = {
                "origin": _t(lang, "Origin"),
                "destination": _t(lang, "Destination"),
                "departure_time": _t(lang, "Departure time"),
                "fare": _t(lang, "Fare"),
            }
            core_fields = [f for f in missing_fields if f != "fare"]
            fare_missing = "fare" in missing_fields

            updates: dict[str, str] = {}
            for f in core_fields:
                updates[f] = st.text_input(label_map.get(f, f), key=f"followup_{f}")

            fare_specify = False
            fare_val = ""
            if fare_missing:
                fare_specify = st.toggle(_t(lang, "fare_toggle"), key="followup_fare_toggle")
                fare_val = st.text_input(
                    label_map["fare"],
                    key="followup_fare",
                    disabled=not fare_specify,
                    placeholder="e.g. max LKR 2000, cheapest",
                )

            submitted = st.form_submit_button("Submit")
            if submitted:
                cleaned: dict[str, str] = {}
                ok = True
                for f in core_fields:
                    v = (updates.get(f) or "").strip()
                    if not v:
                        ok = False
                        break
                    cleaned[f] = v
                if not ok:
                    st.warning(_t(lang, "follow_up_prefix"))
                elif fare_missing:
                    if fare_specify:
                        fv = (fare_val or "").strip()
                        if not fv:
                            ok = False
                            st.warning(_t(lang, "fare_toggle_need_value"))
                        else:
                            cleaned["fare"] = fv
                    else:
                        cleaned["fare"] = "any"
                if ok:
                    _append("assistant", question)
                    _append("user", str(cleaned))
                    out = _resume_with_updates(cleaned)
                    st.session_state.last_state = {k: v for k, v in out.items() if k != "messages"}
                    payload = _maybe_handle_interrupt(out)
                    if payload:
                        st.rerun()
                    else:
                        resp = out.get("response") or ""
                        _append("assistant", resp)
                        st.rerun()

        return

    # Normal chat input
    user_text = st.chat_input("Ask about routes, e.g. “Bus to Kandy”")
    if not user_text:
        return

    _append("user", user_text)
    out = _invoke_initial(user_text)
    st.session_state.last_state = {k: v for k, v in out.items() if k != "messages"}
    payload = _maybe_handle_interrupt(out)
    if payload:
        st.rerun()
    else:
        resp = out.get("response") or ""
        _append("assistant", resp)
        st.rerun()


if __name__ == "__main__":
    main()

