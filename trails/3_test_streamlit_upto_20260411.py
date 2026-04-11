import uuid

import streamlit as st
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from sinhala_input_helpers import SINHALA_KEYBOARD_ROWS, singlish_to_sinhala

from smartmove_hitl import build_app, detect_language, _t

INPUT_MODE_ENGLISH = "English"
INPUT_MODE_SINGLISH = "Singlish → සිංහල"
INPUT_MODE_SINHALA_KB = "සිංහල keyboard"


def _append_sinhala_char(ch: str) -> None:
    st.session_state.sinhala_compose = (st.session_state.get("sinhala_compose") or "") + ch


def _sinhala_backspace() -> None:
    s = st.session_state.get("sinhala_compose") or ""
    st.session_state.sinhala_compose = s[:-1]


def _sinhala_clear() -> None:
    st.session_state.sinhala_compose = ""


def _fu_append(field: str, ch: str) -> None:
    k = f"fu_si_{field}"
    st.session_state[k] = (st.session_state.get(k) or "") + ch


def _fu_backspace(field: str) -> None:
    k = f"fu_si_{field}"
    st.session_state[k] = (st.session_state.get(k) or "")[:-1]


def _fu_clear(field: str) -> None:
    st.session_state[f"fu_si_{field}"] = ""


def _render_follow_up_field(
    field: str,
    label: str,
    input_mode: str,
) -> None:
    """Render one missing-field widget: English / Singlish / Sinhala (matches main chat input mode)."""
    if input_mode == INPUT_MODE_ENGLISH:
        if field == "fare":
            st.text_input(
                label,
                key=f"followup_{field}",
                placeholder="e.g. max LKR 2000, cheapest",
            )
        else:
            st.text_input(label, key=f"followup_{field}")
        return

    if input_mode == INPUT_MODE_SINGLISH:
        st.text_area(f"{label} (Singlish)", key=f"fu_sl_{field}", height=68, placeholder="Romanized Sinhala…")
        raw = (st.session_state.get(f"fu_sl_{field}") or "").strip()
        last_k = f"_fu_sl_last_{field}"
        out_k = f"_fu_sl_si_{field}"
        if raw:
            if st.session_state.get(last_k) != raw:
                st.session_state[last_k] = raw
                st.session_state[out_k] = singlish_to_sinhala(raw)
            si = st.session_state.get(out_k) or ""
            st.caption(f"සිංහල: {si or '—'}")
        else:
            st.session_state[last_k] = ""
            st.session_state[out_k] = ""
            st.caption("සිංහල: —")
        return

    # Sinhala keyboard mode
    st.text_area(label, key=f"fu_si_{field}", height=68)
    c1, c2 = st.columns(2)
    with c1:
        st.button("⌫", key=f"fu_bs_{field}", on_click=_fu_backspace, args=(field,), use_container_width=True)
    with c2:
        st.button("Clear", key=f"fu_clr_{field}", on_click=_fu_clear, args=(field,), use_container_width=True)
    with st.popover(f"⌨ {label}"):
        for ri, row in enumerate(SINHALA_KEYBOARD_ROWS):
            cols = st.columns(len(row))
            for ci, ch in enumerate(row):
                with cols[ci]:
                    lab = ch if ch.strip() else "·"
                    st.button(
                        lab,
                        key=f"fu_sk_{field}_{ri}_{ci}",
                        on_click=_fu_append,
                        args=(field, ch),
                        use_container_width=True,
                    )


def _collect_follow_up_value(field: str, input_mode: str) -> str:
    """Read submitted value for one field from session state (after form submit)."""
    if input_mode == INPUT_MODE_ENGLISH:
        return (st.session_state.get(f"followup_{field}") or "").strip()
    if input_mode == INPUT_MODE_SINGLISH:
        raw = (st.session_state.get(f"fu_sl_{field}") or "").strip()
        if not raw:
            return ""
        si = singlish_to_sinhala(raw).strip()
        return si if si else raw
    return (st.session_state.get(f"fu_si_{field}") or "").strip()


def _ensure_app():
    if "app" not in st.session_state:
        st.session_state.app = build_app()
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"st-{uuid.uuid4().hex}"
    if "history" not in st.session_state:
        st.session_state.history = []
    if "pending_interrupt" not in st.session_state:
        st.session_state.pending_interrupt = None
    if "lang" not in st.session_state:
        st.session_state.lang = "en"
    if "last_state" not in st.session_state:
        st.session_state.last_state = None
    if "sinhala_compose" not in st.session_state:
        st.session_state.sinhala_compose = ""
    if "input_mode" not in st.session_state:
        st.session_state.input_mode = INPUT_MODE_ENGLISH


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

    return st.session_state.app.invoke(state, cfg)


def _resume_with_updates(updates: dict[str, str]):
    cfg = {"configurable": {"thread_id": st.session_state.thread_id}}
    return st.session_state.app.invoke(Command(resume=updates), cfg)


def _maybe_handle_interrupt(out: dict):
    if "__interrupt__" not in out:
        st.session_state.pending_interrupt = None
        return None

    payload = out["__interrupt__"][0].value
    st.session_state.pending_interrupt = payload
    return payload


def _run_user_message(user_text: str):
    if not (user_text or "").strip():
        return
    user_text = user_text.strip()
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


def _render_alternate_input(input_mode: str):
    """Singlish live conversion or Sinhala popover keyboard + send (no st.chat_input)."""
    st.markdown("---")

    user_text: str | None = None

    if input_mode == INPUT_MODE_SINGLISH:
        st.caption("Singlish (romanized Sinhala). Preview converts below on each edit.")
        st.text_area("Singlish", key="singlish_box", height=100, placeholder="e.g. mata kandy yanna one")
        raw = (st.session_state.get("singlish_box") or "").strip()
        last = st.session_state.get("_singlish_last_raw")
        if raw:
            if last != raw:
                st.session_state._singlish_last_raw = raw
                st.session_state._singlish_si_out = singlish_to_sinhala(raw)
            si_preview = st.session_state.get("_singlish_si_out") or ""
        else:
            st.session_state._singlish_last_raw = ""
            st.session_state._singlish_si_out = ""
            si_preview = ""

        st.markdown("**සිංහල (live)**")
        st.text(si_preview if si_preview else "—")

        if st.button("Send message", type="primary", key="send_singlish"):
            user_text = si_preview if si_preview else raw

    elif input_mode == INPUT_MODE_SINHALA_KB:
        st.caption("Type in the box and/or tap characters in the keyboard popover.")
        st.text_area("සිංහල", key="sinhala_compose", height=110)

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            st.button("⌫ Backspace", on_click=_sinhala_backspace, key="si_bs", use_container_width=True)
        with c2:
            st.button("Clear", on_click=_sinhala_clear, key="si_clr", use_container_width=True)

        with st.popover("සිංහල keyboard — tap letters"):
            for ri, row in enumerate(SINHALA_KEYBOARD_ROWS):
                cols = st.columns(len(row))
                for ci, ch in enumerate(row):
                    with cols[ci]:
                        label = ch if ch.strip() else "·"
                        st.button(
                            label,
                            key=f"sk_{ri}_{ci}",
                            on_click=_append_sinhala_char,
                            args=(ch,),
                            use_container_width=True,
                        )

        if st.button("Send message", type="primary", key="send_sinhala"):
            user_text = (st.session_state.get("sinhala_compose") or "").strip()

    if user_text:
        _run_user_message(user_text)


def main():
    st.set_page_config(page_title="SmartMove (LangGraph HITL)", page_icon="🧭", layout="centered")
    _ensure_app()

    st.title("SmartMove")
    st.caption("LangGraph Human-in-the-loop demo (interrupt + resume)")

    with st.sidebar:
        mode_options = [INPUT_MODE_ENGLISH, INPUT_MODE_SINGLISH, INPUT_MODE_SINHALA_KB]
        current = st.session_state.get("input_mode", INPUT_MODE_ENGLISH)
        default_i = mode_options.index(current) if current in mode_options else 0
        input_mode = st.radio(
            "Input language",
            options=mode_options,
            index=default_i,
            key="input_mode_radio",
        )
        st.session_state.input_mode = input_mode
        st.markdown(
            "- **English** — normal chat bar  \n"
            "- **Singlish → සිංහල** — roman text → Sinhala preview + send  \n"
            "- **සිංහල keyboard** — compose in the box; popover adds letters  \n"
            "\nSinglish conversion uses your OpenAI key from `.env`."
        )

    with st.expander("State (latest)", expanded=False):
        st.json(st.session_state.last_state or {})

    _render_chat()

    pending = st.session_state.pending_interrupt
    if pending:
        lang = st.session_state.lang
        input_mode = st.session_state.get("input_mode", INPUT_MODE_ENGLISH)
        question = pending.get("question") or ""
        missing_fields = list(pending.get("missing_fields") or [])

        with st.chat_message("assistant"):
            st.markdown(question)
            st.caption(
                f"Follow-up input mode: **{input_mode}** (same as sidebar). "
                "Change it in the sidebar if needed."
            )

        with st.form("follow_up_form", clear_on_submit=False):
            label_map = {
                "origin": _t(lang, "Origin"),
                "destination": _t(lang, "Destination"),
                "departure_time": _t(lang, "Departure time"),
                "fare": _t(lang, "Fare"),
            }
            core_fields = [f for f in missing_fields if f != "fare"]
            fare_missing = "fare" in missing_fields

            for f in core_fields:
                _render_follow_up_field(f, label_map.get(f, f), input_mode)

            fare_specify = False
            if fare_missing:
                fare_specify = st.toggle(_t(lang, "fare_toggle"), key="followup_fare_toggle")
                if fare_specify:
                    _render_follow_up_field("fare", label_map["fare"], input_mode)

            submitted = st.form_submit_button("Submit")
            if submitted:
                cleaned: dict[str, str] = {}
                ok = True
                for f in core_fields:
                    v = _collect_follow_up_value(f, input_mode)
                    if not v:
                        ok = False
                        break
                    cleaned[f] = v
                if not ok:
                    st.warning(_t(lang, "follow_up_prefix"))
                elif fare_missing:
                    if fare_specify:
                        fv = _collect_follow_up_value("fare", input_mode)
                        if not fv:
                            ok = False
                            st.warning(_t(lang, "fare_toggle_need_value"))
                        else:
                            cleaned["fare"] = fv
                    else:
                        cleaned["fare"] = "any"
                if ok:
                    st.session_state.history.append(("assistant", question))
                    st.session_state.history.append(("user", str(cleaned)))
                    out = _resume_with_updates(cleaned)
                    st.session_state.last_state = {k: v for k, v in out.items() if k != "messages"}
                    payload = _maybe_handle_interrupt(out)
                    if payload:
                        st.rerun()
                    else:
                        resp = out.get("response") or ""
                        st.session_state.history.append(("assistant", resp))
                        st.rerun()

        return

    # Main query input
    if input_mode == INPUT_MODE_ENGLISH:
        user_text = st.chat_input("Ask about routes, e.g. “Bus to Kandy”")
        if user_text:
            _run_user_message(user_text)
    else:
        _render_alternate_input(input_mode)


if __name__ == "__main__":
    main()
