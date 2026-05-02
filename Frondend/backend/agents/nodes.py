"""LangGraph nodes that orchestrate the SmartMove pipeline."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import interrupt

from .cypher import (
    _parse_departure_constraint,
    _parse_fare_intent,
    _title_case_place,
    classify_query_shape,
    cypher_generation_agent,
)
from .extraction import (
    _coerce_extracted_value,
    _heuristic_fare_from_query,
    _sanitize_place_field,
    _value_present,
    extract_fare_from_query,
    extract_transport_fields,
    followup_llm_extract,
    llm_extract_transport_from_query,
    merge_extracted_into_state,
    normalize_datetime,
    normalize_extraction_output,
)
from .i18n import SUPPORTED_LANGS, _t, detect_language, to_english
from .llm import get_llm
from .neo4j_client import execute_neo4j_query
from .state import SmartMoveState


# ---------------------------------------------------------------------------
# Pre-extraction nodes
# ---------------------------------------------------------------------------


def language_detection_node(state: SmartMoveState) -> SmartMoveState:
    original = state.get("user_query_original") or state.get("user_query") or ""
    lang = state.get("language") or detect_language(original)
    user_query_en = to_english(original, lang)
    return {
        **state,
        "language": lang,
        "user_query_original": original,
        "user_query": user_query_en or original,
    }


def intent_detection_node(state: SmartMoveState) -> SmartMoveState:
    query = state.get("user_query") or ""
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are SmartMove intent router.\n"
                "Classify user message into one of: greeting, transport, fallback.\n"
                "Return only one label.",
            ),
            ("human", "{query}"),
        ]
    )
    intent = (prompt | get_llm()).invoke({"query": query}).content.strip().lower()
    if intent not in {"greeting", "transport", "fallback"}:
        intent = "fallback"
    return {**state, "intent": intent}


def greeting_node(state: SmartMoveState) -> SmartMoveState:
    lang = state.get("language") or "en"
    response = _t(lang, "greeting")
    return {
        **state,
        "response": response,
        "messages": state.get("messages", []) + [AIMessage(content=response)],
    }


def fallback_node(state: SmartMoveState) -> SmartMoveState:
    lang = state.get("language") or "en"
    response = _t(lang, "fallback")
    return {
        **state,
        "response": response,
        "messages": state.get("messages", []) + [AIMessage(content=response)],
    }


# ---------------------------------------------------------------------------
# Field extraction nodes
# ---------------------------------------------------------------------------


def llm_extract_node(state: SmartMoveState) -> SmartMoveState:
    q = (state.get("user_query") or "").strip()
    extracted: dict[str, Any] = {}
    if os.getenv("OPENAI_API_KEY") and q:
        try:
            extracted = llm_extract_transport_from_query(q)
        except Exception:
            extracted = {}
    if not extracted:
        extracted = extract_transport_fields(q)
    norm = normalize_extraction_output(extracted)
    if not _value_present(norm.get("fare")):
        hint = _heuristic_fare_from_query(q)
        if hint:
            norm = normalize_extraction_output({**extracted, "fare": hint})
    return {**state, "extracted_data": norm}


def merge_state_node(state: SmartMoveState) -> SmartMoveState:
    ext = state.get("extracted_data") or {}
    merged_fields = merge_extracted_into_state(state, ext)
    return {**state, **merged_fields}


# ---------------------------------------------------------------------------
# Validation + follow-up
# ---------------------------------------------------------------------------


def validate_mandatory_fields(state: SmartMoveState) -> list[str]:
    """Origin + destination always required.

    `departure_time` is only required when the user actually asked about
    schedules / times. `fare` is only required when the user did NOT ask a
    pure schedule question (so we can still apply the fare toggle).
    """
    shape = classify_query_shape(state)
    missing: list[str] = []
    if not state.get("origin"):
        missing.append("origin")
    if not state.get("destination"):
        missing.append("destination")
    if shape != "fare_only" and not state.get("departure_time"):
        missing.append("departure_time")
    if shape != "schedule_only" and not state.get("fare"):
        missing.append("fare")
    return missing


def missing_info_validator_node(state: SmartMoveState) -> SmartMoveState:
    return {**state, "missing_fields": validate_mandatory_fields(state)}


def _regex_followup_updates(state: SmartMoveState, missing: list[str], user_input: Any) -> dict[str, str | None]:
    """Original dict / regex follow-up path (fallback)."""
    lang = state.get("language") or "en"
    if isinstance(user_input, dict):
        updates: dict[str, str | None] = {}
        for field in missing:
            if state.get(field):
                continue
            v = user_input.get(field)
            if isinstance(v, str) and v.strip():
                v_en = to_english(v, lang)
                if field in {"origin", "destination"}:
                    p = _sanitize_place_field(v_en)
                    if p:
                        updates[field] = p
                elif field == "departure_time":
                    updates[field] = normalize_datetime(v_en) or v_en.strip().lower()
                elif field == "fare":
                    coerced = _coerce_extracted_value("fare", v_en)
                    updates[field] = coerced or v_en.strip()
                else:
                    updates[field] = v_en.strip()
        return updates

    user_text = str(user_input).strip()
    user_text_en = to_english(user_text, lang)
    extracted = extract_transport_fields(user_text_en)
    updates2: dict[str, str | None] = {}
    for field in missing:
        if state.get(field):
            continue
        value = extracted.get(field)
        if not value:
            if field in {"origin", "destination"}:
                value = _sanitize_place_field(user_text_en)
            elif field == "departure_time":
                value = normalize_datetime(user_text_en) or user_text_en.strip().lower() or None
            elif field == "fare":
                value = extract_fare_from_query(user_text_en) or (user_text_en.strip() or None)
        if value:
            updates2[field] = value
    return updates2


def _extract_missing_field_updates(state: SmartMoveState, missing: list[str], user_input: Any) -> dict[str, str | None]:
    regex_updates = _regex_followup_updates(state, missing, user_input)
    if isinstance(user_input, dict):
        return regex_updates
    user_text = str(user_input).strip()
    llm_updates: dict[str, str | None] = {}
    if os.getenv("OPENAI_API_KEY") and user_text:
        try:
            llm_updates = followup_llm_extract(state, user_text)
        except Exception:
            llm_updates = {}
    merged = dict(regex_updates)
    for k, v in llm_updates.items():
        if v:
            merged[k] = v
    return merged


def follow_up_question_node(state: SmartMoveState) -> SmartMoveState:
    missing = state.get("missing_fields") or []
    lang = state.get("language") or "en"
    field_map = {
        "origin": _t(lang, "origin"),
        "destination": _t(lang, "destination"),
        "departure_time": _t(lang, "departure_time"),
        "fare": _t(lang, "fare"),
    }
    missing_text = ", ".join(field_map.get(f, f) for f in missing)
    response = f"{_t(lang, 'follow_up_prefix')}: {missing_text}."

    human_reply = interrupt(
        {"kind": "follow_up_question", "question": response, "missing_fields": missing}
    )
    updates = _extract_missing_field_updates(state, missing, human_reply)

    messages = state.get("messages", []) + [AIMessage(content=response)]
    messages = messages + [HumanMessage(content=str(human_reply).strip())]

    return {
        **state,
        **updates,
        "follow_up_question": response,
        "response": response,
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# Cypher / Neo4j / response
# ---------------------------------------------------------------------------


def cypher_generator_node(state: SmartMoveState) -> SmartMoveState:
    """Thin wrapper to expose the cypher agent under a stable node name."""
    return cypher_generation_agent(state)


def neo4j_query_node(state: SmartMoveState) -> SmartMoveState:
    return {**state, "result": execute_neo4j_query(state.get("cypher_query") or "")}


_RESPONSE_FORMATTER_SYSTEM = """You are SmartMove's Response Formatter Agent operating in RAG mode.

ROLE
You receive the user's question plus a small set of retrieved Neo4j rows
(`context.rows`) that the upstream Cypher agent already filtered and ordered.
Treat those rows as your ONLY ground truth — exactly like a RAG retrieval set.
Compose a final answer that is what the user actually asked for, in their
language, honouring their preferences.

LANGUAGE LOCK
- Respond ONLY in {lang_name} ({lang_code}). Never mix languages.
- Mirror the user's tone (formal vs casual) from `user_query`.
- Place names follow the source script (e.g. "Colombo" -> "කොළඹ" in Sinhala);
  keep clock times as numerals like 06:15 / 20:30.

DEDUPLICATION (CRITICAL)
- `context.rows` is ALREADY deduplicated upstream. Every row you see is a
  distinct option — never restate the same fare / departure / route twice.
- If multiple rows still share the SAME displayable fact (e.g. all have
  fare = LKR 1195 across different schedules), do NOT list it multiple times.
  Mention the value ONCE. You may add a brief qualifier like
  "(consistent across services)" if appropriate.
- Count distinct facts before you write. A list of 4 identical fares should
  collapse into a single sentence, not 4 bullet points.

ANSWER SHAPE — pick whichever serves the user's intent AND the row count:
A. SINGLE-FACT shape (rows collapse to ONE distinct fact, OR user asked
   "single best option" — cheapest / earliest / latest / specific fare lookup):
   - One or two direct sentences naming the fact.
   - Examples (Sinhala): "අනුරාධපුර සිට කොළඹට ගාස්තුව **LKR 1195** වේ."
   - Examples (English): "The fare from Anuradhapura to Colombo is **LKR 1195**."
   - For a winning schedule row: "The earliest bus is **06:15 → 09:30**, fare `LKR 450`."
   - NO bullet list. NO repetition.
B. BROWSE shape (rows contain MULTIPLE genuinely-distinct facts):
   - One short intro sentence (mention origin -> destination).
   - Markdown numbered list (`1.` / `2.` / ...) — at most {max_rows} entries,
     in the order rows are given. Each line:
       "**HH:MM → HH:MM** — <qualifiers>"
     Append fare when allowed: " — `LKR <fare>`".
   - Each list item must convey something the previous one didn't.
   - Optional one-line closing tip (e.g. "Cheapest option listed first.").

FARE PREFERENCE — fare_intent.mode = `{fare_mode}`:
- "cheapest" -> Always cite fare per option. Call out the top row as the cheapest.
- "budget"   -> Always cite fare per option. Flag the cheapest in-budget pick.
- "any"      -> Cite fare per option, neutrally. Don't editorialise.
- "skip"     -> NEVER mention price, fare, cost, LKR, or budget anywhere.

EMPTY ROWS
- Apologise briefly and suggest ONE concrete tweak (a different time,
  transport, or fare preference). Do NOT invent rows.

RETRIEVAL ERROR (`context.error` not null)
- Apologise briefly and explain the issue in plain language. Do NOT show
  the raw error or any Cypher / stack traces.

ABSOLUTE RULES
- Use ONLY facts present in `context.rows`. No fabrication of places, times,
  fares, or transport types.
- No JSON, no Cypher, no markdown fences around the whole response,
  no "as an AI" preambles.
- Keep it tight — concise is better than complete.
"""


_RESPONSE_FORMATTER_USER = """user_query (LANGUAGE={lang_code}):
{user_query_original}

user_query_english:
{user_query_english}

preferences:
{preferences_json}

context:
{context_json}
"""


def _parse_result_payload(raw: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """Convert the JSON-string returned by `execute_neo4j_query` into rows + optional error."""
    if raw is None:
        return [], "No result available."
    s = str(raw).strip()
    if not s:
        return [], "No result available."
    if s.startswith(("Neo4j query error", "Neo4j not configured", "No Cypher query")):
        return [], s
    try:
        data = json.loads(s)
    except Exception:
        return [], s
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)], None
    return [], "Unexpected result shape."


_ROW_FIELDS = (
    "origin",
    "destination",
    "departure_time",
    "arrival_time",
    "departure",
    "arrival",
    "departure_from_terminal",
    "arrival_to_terminal",
    "route_type",
    "service_type",
    "route_no",
    "fare",
)


def _row_signature(row: dict[str, Any]) -> tuple:
    """Stable signature of a row across the fields the user actually sees.

    Two rows with the same origin/destination/departure/arrival/route info AND
    the same fare collapse to one entry — so we never tell the user the same
    "LKR 1195" four times in a row.
    """
    norm = []
    for k in _ROW_FIELDS:
        v = row.get(k)
        if isinstance(v, str):
            norm.append(v.strip().lower())
        elif isinstance(v, (int, float)):
            norm.append(float(v))
        else:
            norm.append(v)
    return tuple(norm)


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order-preserving dedupe by `_row_signature`."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        sig = _row_signature(r)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(r)
    return out


def _trim_rows_for_prompt(
    rows: list[dict[str, Any]], max_rows: int = 8
) -> list[dict[str, Any]]:
    """Project to display fields, dedupe, and cap row count.

    Dedupe BEFORE the cap so a Neo4j result of 5 identical fares doesn't kick
    out a different (unique) option that came after.
    """
    projected: list[dict[str, Any]] = []
    for row in rows:
        item = {k: row.get(k) for k in _ROW_FIELDS if row.get(k) not in (None, "")}
        if item:
            projected.append(item)
    deduped = _dedupe_rows(projected)
    return deduped[:max_rows]


def _build_preferences(state: SmartMoveState) -> dict[str, Any]:
    """Structured preference snapshot the formatter LLM consumes as part of the RAG prompt."""
    op, time_24 = _parse_departure_constraint(state.get("departure_time"))
    fare_intent = _parse_fare_intent(state.get("fare"))
    return {
        "origin": _title_case_place(state.get("origin")) or None,
        "destination": _title_case_place(state.get("destination")) or None,
        "departure_constraint": (
            {"op": op, "time": time_24} if op and time_24 else None
        ),
        "departure_time_raw": state.get("departure_time"),
        "transport_type": state.get("transport_type"),
        "fare_raw": state.get("fare"),
        "fare_intent": fare_intent,
    }


def response_formatter_node(state: SmartMoveState) -> SmartMoveState:
    """RAG-style synthesis: rows are context, the user's query is the question."""
    user_query_original = (
        state.get("user_query_original") or state.get("user_query") or ""
    )
    user_query_english = state.get("user_query") or user_query_original
    raw_result = state.get("result") or ""
    lang_code = state.get("language") or "en"
    lang_name = SUPPORTED_LANGS.get(lang_code, "English")

    preferences = _build_preferences(state)
    fare_mode = preferences["fare_intent"].get("mode", "skip")

    rows, error = _parse_result_payload(raw_result)
    trimmed = _trim_rows_for_prompt(rows, max_rows=8)
    context_block: dict[str, Any] = {"rows": trimmed, "error": error}

    prompt = ChatPromptTemplate.from_messages(
        [("system", _RESPONSE_FORMATTER_SYSTEM), ("human", _RESPONSE_FORMATTER_USER)]
    )

    response = ""
    if os.getenv("OPENAI_API_KEY"):
        try:
            response = (prompt | get_llm()).invoke(
                {
                    "lang_name": lang_name,
                    "lang_code": lang_code,
                    "fare_mode": fare_mode,
                    "max_rows": 8,
                    "user_query_original": user_query_original,
                    "user_query_english": user_query_english,
                    "preferences_json": json.dumps(
                        preferences, ensure_ascii=False, indent=2
                    ),
                    "context_json": json.dumps(
                        context_block, ensure_ascii=False, indent=2, default=str
                    ),
                }
            ).content
        except Exception:
            response = ""

    response = (response or "").strip() or _fallback_response(
        lang_code,
        fare_mode,
        preferences.get("origin") or state.get("origin") or "?",
        preferences.get("destination") or state.get("destination") or "?",
        trimmed,
        error,
    )

    return {
        **state,
        "response": response,
        "messages": state.get("messages", []) + [AIMessage(content=response)],
    }


def _fallback_response(
    lang_code: str,
    fare_mode: str,
    origin: str,
    destination: str,
    rows: list[dict[str, Any]],
    error: str | None,
) -> str:
    """Deterministic Markdown fallback when the LLM is unavailable or empty."""
    if error and not rows:
        prefix = {
            "en": "Sorry, I couldn't fetch results",
            "si": "කණගාටුයි, ප්‍රතිඵල ලබා ගත නොහැකි විය",
            "ta": "மன்னிக்கவும், முடிவுகளை பெற முடியவில்லை",
        }.get(lang_code, "Sorry, I couldn't fetch results")
        return f"{prefix}: {error}"

    if not rows:
        msg = {
            "en": (
                f"No matching options were found from **{origin}** to **{destination}**. "
                "Try a different departure time, transport type, or fare preference."
            ),
            "si": (
                f"**{origin}** සිට **{destination}** දක්වා ගැලපෙන විකල්ප හමු නොවීය. "
                "වෙනත් වේලාවක්, ප්‍රවාහන වර්ගයක්, හෝ ගාස්තු මනාපයක් උත්සාහ කරන්න."
            ),
            "ta": (
                f"**{origin}** -> **{destination}** ஐக் கொண்டு பொருந்தும் "
                "விருப்பங்கள் எதுவும் இல்லை. வேறு நேரம், போக்குவரத்து, அல்லது "
                "கட்டண விருப்பத்தை முயற்சிக்கவும்."
            ),
        }
        return msg.get(lang_code, msg["en"])

    has_schedule = any(
        r.get("departure_time") or r.get("departure") for r in rows
    )

    # Single-fact case ----------------------------------------------------
    # When upstream dedupe has already collapsed everything to one row, OR the
    # rows differ only in a field the user didn't ask about, give a tight
    # one-sentence answer.
    if len(rows) == 1:
        row = rows[0]
        if not has_schedule and fare_mode != "skip" and row.get("fare") is not None:
            single = {
                "en": f"The fare from **{origin}** to **{destination}** is `LKR {row['fare']}`.",
                "si": f"**{origin}** සිට **{destination}** දක්වා ගාස්තුව **LKR {row['fare']}** වේ.",
                "ta": f"**{origin}** -> **{destination}** கட்டணம் **LKR {row['fare']}** ஆகும்.",
            }
            return single.get(lang_code, single["en"])
        if has_schedule:
            dep = row.get("departure_time") or row.get("departure") or "?"
            arr = row.get("arrival_time") or row.get("arrival") or "?"
            qual_parts = [
                str(v)
                for v in (row.get("route_type"), row.get("service_type"), row.get("route_no"))
                if v
            ]
            qualifiers = f" ({' / '.join(qual_parts)})" if qual_parts else ""
            fare_suffix = ""
            if fare_mode != "skip" and row.get("fare") is not None:
                fare_suffix = f", `LKR {row['fare']}`"
            single_sched = {
                "en": f"From **{origin}** to **{destination}**: **{dep} → {arr}**{qualifiers}{fare_suffix}.",
                "si": f"**{origin}** සිට **{destination}**: **{dep} → {arr}**{qualifiers}{fare_suffix}.",
                "ta": f"**{origin}** -> **{destination}**: **{dep} → {arr}**{qualifiers}{fare_suffix}.",
            }
            return single_sched.get(lang_code, single_sched["en"])

    # Browse / multiple-fact case ---------------------------------------
    intro = {
        "en": f"Here are options from **{origin}** to **{destination}**:",
        "si": f"**{origin}** සිට **{destination}** දක්වා විකල්ප මෙන්න:",
        "ta": f"**{origin}** -> **{destination}** விருப்பங்கள்:",
    }.get(lang_code, f"Here are options from **{origin}** to **{destination}**:")

    bullets: list[str] = []
    for i, row in enumerate(rows):
        if has_schedule:
            dep = row.get("departure_time") or row.get("departure") or "?"
            arr = row.get("arrival_time") or row.get("arrival") or "?"
            qual_parts = [
                str(v)
                for v in (row.get("route_type"), row.get("service_type"), row.get("route_no"))
                if v
            ]
            qualifiers = f" — {' / '.join(qual_parts)}" if qual_parts else ""
            line = f"{i + 1}. **{dep} → {arr}**{qualifiers}"
        else:
            line = f"{i + 1}."

        if fare_mode != "skip" and row.get("fare") is not None:
            tag = ""
            if i == 0 and fare_mode in ("cheapest", "budget"):
                tag = (
                    " _(cheapest)_"
                    if fare_mode == "cheapest"
                    else " _(cheapest within budget)_"
                )
            sep = " — " if has_schedule else " "
            line += f"{sep}`LKR {row['fare']}`{tag}"
        bullets.append(line.strip())

    return "\n".join([intro, *bullets])


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


def route_intent(state: SmartMoveState) -> Literal["greeting", "transport", "fallback"]:
    return state.get("intent") or "fallback"


def route_missing_info(state: SmartMoveState) -> Literal["follow_up", "continue"]:
    return "follow_up" if (state.get("missing_fields") or []) else "continue"
