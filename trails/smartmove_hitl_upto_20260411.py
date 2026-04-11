"""
Reusable SmartMove LangGraph (Human-in-the-loop) components.

- Importable by Streamlit, scripts, or tests
- CLI wrapper lives in `trails/3_test.py`
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal
from typing_extensions import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

load_dotenv()

OPENAI_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

SUPPORTED_LANGS: dict[str, str] = {"en": "English", "si": "Sinhala", "ta": "Tamil"}


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(model=OPENAI_MODEL, temperature=OPENAI_TEMPERATURE)


def _t(lang: str, key: str) -> str:
    l = lang if lang in SUPPORTED_LANGS else "en"
    table: dict[str, dict[str, str]] = {
        "en": {
            "cli_title": "SmartMove CLI (type 'exit' to quit)",
            "you": "You",
            "smartmove": "SmartMove",
            "warn_no_key": "Warning: OPENAI_API_KEY not set. Please set it in your .env file.",
            "greeting": "Welcome to SmartMove. I can help with routes, schedules, and transport options.",
            "fallback": "SmartMove supports transportation queries only. Please ask about routes, stations, or travel options.",
            "follow_up_prefix": "Please provide the following required details",
            "origin": "origin",
            "destination": "destination",
            "departure_time": "departure time",
            "Origin": "Origin",
            "Destination": "Destination",
            "Departure time": "Departure time",
            "fare": "fare / budget",
            "Fare": "Fare (e.g. max LKR 2000, cheapest, or any)",
            "fare_toggle": "Specify fare or budget preference",
            "fare_toggle_need_value": "Enter a fare or budget preference, or turn off the toggle.",
        },
        "si": {
            "cli_title": "SmartMove CLI (ඉවත් වීමට 'exit' ටයිප් කරන්න)",
            "you": "ඔබ",
            "smartmove": "SmartMove",
            "warn_no_key": "අවවාදයයි: OPENAI_API_KEY සකසා නැත. කරුණාකර ඔබගේ .env ගොනුවේ සකසන්න.",
            "greeting": "SmartMove වෙත සාදරයෙන් පිළිගනිමු. මාර්ග, කාලසටහන් සහ ප්‍රවාහන විකල්ප ගැන ඔබට උපකාර කළ හැක.",
            "fallback": "SmartMove ප්‍රවාහන සම්බන්ධ ප්‍රශ්න සඳහා පමණක් සහාය දක්වයි. කරුණාකර මාර්ග/ස්ථාන/ගමන් විකල්ප ගැන අහන්න.",
            "follow_up_prefix": "කරුණාකර අවශ්‍ය විස්තර ලබා දෙන්න",
            "origin": "ආරම්භ ස්ථානය",
            "destination": "ගමනාන්තය",
            "departure_time": "පිටත්වෙන වේලාව",
            "Origin": "ආරම්භ ස්ථානය",
            "Destination": "ගමනාන්තය",
            "Departure time": "පිටත්වෙන වේලාව",
            "fare": "ගාස්තුව / අයවැය",
            "Fare": "ගාස්තුව (උදා: උපරිම LKR 2000, ලාභම, හෝ ඕනෑම)",
            "fare_toggle": "ගාස්තුව හෝ අයවැය මනාපයක් සඳහන් කරන්න",
            "fare_toggle_need_value": "ගාස්තුව ඇතුළත් කරන්න, නැතහොත් ටොගල් ක්‍රියාවිරහිත කරන්න.",
        },
        "ta": {
            "cli_title": "SmartMove CLI ('exit' என টাইப் செய்து வெளியேறலாம்)",
            "you": "நீங்கள்",
            "smartmove": "SmartMove",
            "warn_no_key": "எச்சரிக்கை: OPENAI_API_KEY அமைக்கப்படவில்லை. உங்கள் .env கோப்பில் அமைக்கவும்.",
            "greeting": "SmartMove-க்கு வரவேற்கிறோம். வழிகள், நேர அட்டவணை மற்றும் போக்குவரத்து விருப்பங்களில் உதவலாம்.",
            "fallback": "SmartMove போக்குவரத்து தொடர்பான கேள்விகளுக்கே ஆதரவு தருகிறது. வழிகள்/நிலையங்கள்/பயண விருப்பங்கள் பற்றி கேளுங்கள்.",
            "follow_up_prefix": "தேவையான விவரங்களை வழங்கவும்",
            "origin": "தொடக்க இடம்",
            "destination": "இலக்கு",
            "departure_time": "புறப்படும் நேரம்",
            "Origin": "தொடக்க இடம்",
            "Destination": "இலக்கு",
            "Departure time": "புறப்படும் நேரம்",
            "fare": "கட்டணம் / பட்ஜெட்",
            "Fare": "கட்டணம் (எ.கா: அதிகபட்சம் LKR 2000, மலிவானது, அல்லது எதுவும்)",
            "fare_toggle": "கட்டணம் அல்லது பட்ஜெட் விருப்பத்தைக் குறிப்பிடவும்",
            "fare_toggle_need_value": "கட்டணத்தை உள்ளிடவும், அல்லது டாகிளை அணைக்கவும்.",
        },
    }
    return table.get(l, table["en"]).get(key, table["en"].get(key, key))


def detect_language(user_text: str) -> str:
    text = (user_text or "").strip()
    if not text:
        return "en"
    if re.search(r"[\u0D80-\u0DFF]", text):
        return "si"
    if re.search(r"[\u0B80-\u0BFF]", text):
        return "ta"

    if os.getenv("OPENAI_API_KEY"):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "Detect the user's language. Return only one of: en, si, ta. If unsure, return en."),
                ("human", "{text}"),
            ]
        )
        try:
            code = (prompt | get_llm()).invoke({"text": text}).content.strip().lower()
            if code in SUPPORTED_LANGS:
                return code
        except Exception:
            pass
    return "en"


class SmartMoveState(TypedDict):
    messages: Annotated[list[Any], add_messages]

    user_query: str
    user_query_original: str | None
    language: str | None
    intent: str | None

    origin: str | None
    destination: str | None
    departure_time: str | None
    date: str | None
    transport_type: str | None
    fare: str | None

    missing_fields: list[str] | None

    cypher_query: str | None
    result: str | None
    response: str | None
    follow_up_question: str | None


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


def to_english(text: str, source_lang: str) -> str:
    """Translate to English for state updates/extraction. If already English, return as-is."""
    t = (text or "").strip()
    if not t:
        return ""
    if source_lang == "en":
        return t

    # If no API key, we can't translate reliably; keep original.
    if not os.getenv("OPENAI_API_KEY"):
        return t

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Translate the user text to English.\n"
                "- Preserve place names (transliterate if needed).\n"
                "- Preserve times/dates.\n"
                "- Return only the translated text, no quotes.",
            ),
            ("human", "{text}"),
        ]
    )
    try:
        return (prompt | get_llm()).invoke({"text": t}).content.strip()
    except Exception:
        return t


def normalize_datetime(raw_text: str) -> str | None:
    if not raw_text:
        return None
    rel = re.search(r"\b(after|before)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", raw_text, re.IGNORECASE)
    if rel:
        return f"{rel.group(1).lower()} {rel.group(2).lower()}"
    m = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)?)", raw_text)
    if m:
        return m.group(1)
    m2 = re.search(r"(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?)", raw_text)
    if m2:
        return m2.group(1)
    t = re.search(r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", raw_text, re.IGNORECASE)
    if t:
        return t.group(1).lower()
    return None


def _clean_place(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    cleaned = re.sub(r"^(?:the\s+)?city\s+of\s+", "", cleaned, flags=re.IGNORECASE)
    while True:
        next_cleaned = re.sub(
            r"^(?:need\s+to\s+|go\s+to\s+|go\s+|travel\s+to\s+|travel\s+|reach\s+|get\s+to\s+|get\s+)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        if next_cleaned == cleaned:
            break
        cleaned = next_cleaned
    return cleaned.strip() or None


def _looks_like_place_name(raw: str | None) -> bool:
    """Reject generic travel phrases and non-location text; keep plausible place tokens."""
    if not raw:
        return False
    t = re.sub(r"\s+", " ", raw.strip().lower())
    if len(t) < 2 or len(t) > 80:
        return False

    # Whole-string or obvious phrase: not a location
    if re.fullmatch(
        r"(on\s+)?a\s+trip|on\s+a\s+trip|trip|trips?|vacation|holiday|journey|"
        r"plan\s+a\s+trip|go\s+on\s+a\s+trip|for\s+a\s+trip|take\s+a\s+trip|"
        r"travel(ing)?|touring|sightseeing|outing|abroad|home|there|here|work|office|"
        r"go|going|get|getting|come|coming|leave|leaving|back|away",
        t,
    ):
        return False

    if re.search(
        r"\b(on\s+a\s+trip|a\s+trip\b|plan\s+a\s+trip|go\s+on\s+a\s+trip|for\s+a\s+trip)\b",
        t,
    ):
        return False

    words = t.split()
    if len(words) > 5:
        return False

    # Multi-word junk (articles / prepositions only + "trip" etc.)
    junk_only = {"on", "a", "the", "to", "for", "in", "at", "my", "your", "our", "an", "and", "or", "of", "is", "it"}
    trip_words = {"trip", "trips", "travel", "vacation", "holiday", "journey", "tour", "tours", "planning"}
    if len(words) >= 2 and all(w in junk_only | trip_words for w in words):
        return False

    return True


def _sanitize_place_field(value: str | None) -> str | None:
    cleaned = _clean_place(value)
    if cleaned is None:
        return None
    return cleaned if _looks_like_place_name(cleaned) else None


def _extract_travel_date(text: str) -> str | None:
    """Date-only part (not the same as clock time). Complements departure_time."""
    if not text:
        return None
    # ISO date
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    # "8 August 2024" style (date, not time)
    m2 = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", text)
    if m2:
        return m2.group(1).strip()
    return None


def extract_fare_from_query(text: str) -> str | None:
    """Infer fare / budget / price intent from English (or translated) query text."""
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()

    if re.search(r"\b(cheapest|lowest\s+(?:price|fare)|economy(?:\s+option)?)\b", low):
        return "cheapest"
    if re.search(r"\b(any\s+price|don'?t\s+care|no\s+budget|no\s+limit|price\s+doesn'?t\s+matter)\b", low):
        return "any"

    m = re.search(
        r"\b(?:under|below|less\s+than|max(?:imum)?|up\s*to|upto|<=)\s*(?:lkr|rs\.?|rupees?)?\s*([\d,]+(?:\.\d+)?)\b",
        low,
    )
    if m:
        return f"max LKR {m.group(1).replace(',', '')}"

    m2 = re.search(r"\bbudget\s*(?:of|:)?\s*(?:lkr|rs\.?)?\s*([\d,]+(?:\.\d+)?)\b", low)
    if m2:
        return f"budget LKR {m2.group(1).replace(',', '')}"

    m3 = re.search(r"\b(?:lkr|rs\.?)\s*([\d,]+(?:\.\d+)?)\b(?:\s*(?:max|budget|limit))?\b", low)
    if m3 and re.search(r"\b(?:budget|max|under|below|limit|fare|price|cost)\b", low):
        return f"budget LKR {m3.group(1).replace(',', '')}"

    if re.search(
        r"\b(how\s+much|what'?s?\s+the\s+fare|what\s+is\s+the\s+fare|ticket\s+price|cost\s+of|fare\s+for|prices?\s+for|include\s+(?:the\s+)?(?:fare|price|cost))\b",
        low,
    ):
        return "include_prices"

    return None


def extract_transport_fields(user_query: str) -> dict[str, str | None]:
    text = user_query or ""

    transport_type = None
    for t in ["bus", "train", "car", "taxi", "metro", "flight", "ferry"]:
        if re.search(rf"\b{t}\b", text, re.IGNORECASE):
            transport_type = t
            break

    origin = None
    destination = None

    go_from = re.search(
        r"(?:go(?:\s+to)?|travel(?:\s+to)?|reach|get(?:\s+to)?)\s+([A-Za-z\s]+?)\s+from\s+([A-Za-z\s]+?)(?:$|\s+(?:on|at|by|for|after|before)\b)",
        text,
        re.IGNORECASE,
    )
    if go_from:
        destination = go_from.group(1).strip()
        origin = go_from.group(2).strip()

    if not (origin and destination):
        from_to = re.search(
            r"from\s+([A-Za-z\s]+?)\s+to\s+([A-Za-z\s]+?)(?:$|\s+(?:on|at|by|for|after|before)\b)",
            text,
            re.IGNORECASE,
        )
        if from_to:
            origin = from_to.group(1).strip()
            destination = from_to.group(2).strip()

    if not (origin and destination):
        to_from = re.search(
            r"\bto\s+([A-Za-z\s]+?)\s+from\s+([A-Za-z\s]+?)(?:$|\s+(?:on|at|by|for|after|before)\b)",
            text,
            re.IGNORECASE,
        )
        if to_from:
            destination = to_from.group(1).strip()
            origin = to_from.group(2).strip()

    # "bus to Kandy", "a train to Colombo", "flight to London"
    if not destination:
        transport_to = re.search(
            r"\b(?:a\s+)?(?:bus|train|car|taxi|metro|flight|ferry)\s+to\s+([A-Za-z][A-Za-z\s]*?)(?:$|\s+(?:on|at|by|for|after|before|from)\b)",
            text,
            re.IGNORECASE,
        )
        if transport_to:
            destination = transport_to.group(1).strip()

    if not destination:
        to_match = re.search(
            r"(?:go|travel|reach|get)\s+to\s+([A-Za-z\s]+?)(?:$|\s+(?:on|at|by|for|after|before)\b)",
            text,
            re.IGNORECASE,
        )
        if to_match:
            destination = to_match.group(1).strip()

    # Do not use a loose "go <anything>" or bare "to <anything>" — they capture phrases like "on a trip".

    origin = _sanitize_place_field(origin)
    destination = _sanitize_place_field(destination)

    departure_time = normalize_datetime(text)
    date_val = _extract_travel_date(text)
    if not date_val and departure_time:
        dm = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\s+\d{2}:\d{2})?$", departure_time.strip())
        if dm:
            date_val = dm.group(1)
    if not date_val:
        date_val = departure_time

    fare = extract_fare_from_query(text)

    return {
        "origin": origin,
        "destination": destination,
        "departure_time": departure_time,
        "date": date_val,
        "transport_type": transport_type,
        "fare": fare,
    }


def validate_mandatory_fields(state: SmartMoveState) -> list[str]:
    missing: list[str] = []
    if not state.get("origin"):
        missing.append("origin")
    if not state.get("destination"):
        missing.append("destination")
    if not state.get("departure_time"):
        missing.append("departure_time")
    if not state.get("fare"):
        missing.append("fare")
    return missing


def generate_cypher_for_transport(state: SmartMoveState) -> str:
    transport = state.get("transport_type") or "any"
    origin = state.get("origin") or "<origin>"
    destination = state.get("destination") or "<destination>"
    departure = state.get("departure_time") or "<departure_time>"
    fare = state.get("fare") or "<fare>"

    return (
        "MATCH (o:Location {name: $origin})-[:CONNECTS]->(r:Route)-[:CONNECTS]->(d:Location {name: $destination}) "
        "WHERE ($transport = 'any' OR r.transport_type = $transport) "
        "RETURN o.name AS origin, d.name AS destination, r.transport_type AS transport_type, "
        "$departure AS departure_time, r.duration AS duration, r.price AS price, "
        "$fare AS fare_preference"
    ).replace("$origin", f"'{origin}'").replace("$destination", f"'{destination}'").replace("$transport", f"'{transport}'").replace("$departure", f"'{departure}'").replace("$fare", f"'{fare}'")


def execute_neo4j_safe(_: str) -> str:
    return (
        "MockResult: 2 routes found | "
        "[{'origin': 'Colombo', 'destination': 'Kandy', 'transport_type': 'bus', 'duration': '3h', 'price': 'LKR 1200'}, "
        "{'origin': 'Colombo', 'destination': 'Kandy', 'transport_type': 'train', 'duration': '2h 30m', 'price': 'LKR 1500'}]"
    )


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
    return {**state, "response": response, "messages": state.get("messages", []) + [AIMessage(content=response)]}


def fallback_node(state: SmartMoveState) -> SmartMoveState:
    lang = state.get("language") or "en"
    response = _t(lang, "fallback")
    return {**state, "response": response, "messages": state.get("messages", []) + [AIMessage(content=response)]}


def query_understanding_node(state: SmartMoveState) -> SmartMoveState:
    extracted = extract_transport_fields(state.get("user_query") or "")
    merged = {
        "origin": state.get("origin") or extracted.get("origin"),
        "destination": state.get("destination") or extracted.get("destination"),
        "departure_time": state.get("departure_time") or extracted.get("departure_time"),
        "date": state.get("date") or extracted.get("date"),
        "transport_type": state.get("transport_type") or extracted.get("transport_type"),
        "fare": state.get("fare") or extracted.get("fare"),
    }
    return {**state, **merged}


def missing_info_validator_node(state: SmartMoveState) -> SmartMoveState:
    return {**state, "missing_fields": validate_mandatory_fields(state)}


def _extract_missing_field_updates(state: SmartMoveState, missing: list[str], user_input: Any) -> dict[str, str | None]:
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
                    updates[field] = extract_fare_from_query(v_en) or v_en.strip()
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

    human_reply = interrupt({"kind": "follow_up_question", "question": response, "missing_fields": missing})
    updates = _extract_missing_field_updates(state, missing, human_reply)

    messages = state.get("messages", []) + [AIMessage(content=response)]
    messages = messages + [HumanMessage(content=str(human_reply).strip())]

    return {**state, **updates, "follow_up_question": response, "response": response, "messages": messages}


def cypher_generator_node(state: SmartMoveState) -> SmartMoveState:
    return {**state, "cypher_query": generate_cypher_for_transport(state)}


def neo4j_query_node(state: SmartMoveState) -> SmartMoveState:
    return {**state, "result": execute_neo4j_safe(state.get("cypher_query") or "")}


def response_formatter_node(state: SmartMoveState) -> SmartMoveState:
    query = state.get("user_query") or ""
    result = state.get("result") or "No result"
    lang = state.get("language") or "en"
    lang_name = SUPPORTED_LANGS.get(lang, "English")
    fare = state.get("fare") or ""

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are SmartMove response formatter.\n"
                "Create a concise transportation-focused answer from the result.\n"
                "Respect the user's fare preference when comparing options (cheapest, max budget, include prices).\n"
                "No filler text.\n"
                f"Respond in {lang_name}.",
            ),
            ("human", "Query: {query}\nFare preference: {fare}\nResult: {result}"),
        ]
    )
    response = (prompt | get_llm()).invoke({"query": query, "result": result, "fare": fare or "not specified"}).content
    return {**state, "response": response, "messages": state.get("messages", []) + [AIMessage(content=response)]}


def route_intent(state: SmartMoveState) -> Literal["greeting", "transport", "fallback"]:
    return state.get("intent") or "fallback"


def route_missing_info(state: SmartMoveState) -> Literal["follow_up", "continue"]:
    return "follow_up" if (state.get("missing_fields") or []) else "continue"


def build_app():
    graph = StateGraph(SmartMoveState)
    graph.add_node("language_detection", language_detection_node)
    graph.add_node("intent_detection", intent_detection_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("query_understanding", query_understanding_node)
    graph.add_node("missing_info_validator", missing_info_validator_node)
    graph.add_node("follow_up_question", follow_up_question_node)
    graph.add_node("cypher_generator", cypher_generator_node)
    graph.add_node("neo4j_query", neo4j_query_node)
    graph.add_node("response_formatter", response_formatter_node)

    graph.add_edge(START, "language_detection")
    graph.add_edge("language_detection", "intent_detection")
    graph.add_conditional_edges("intent_detection", route_intent, {"greeting": "greeting", "transport": "query_understanding", "fallback": "fallback"})
    graph.add_edge("greeting", END)
    graph.add_edge("fallback", END)

    graph.add_edge("query_understanding", "missing_info_validator")
    graph.add_conditional_edges("missing_info_validator", route_missing_info, {"follow_up": "follow_up_question", "continue": "cypher_generator"})
    graph.add_edge("follow_up_question", "missing_info_validator")

    graph.add_edge("cypher_generator", "neo4j_query")
    graph.add_edge("neo4j_query", "response_formatter")
    graph.add_edge("response_formatter", END)

    return graph.compile(checkpointer=MemorySaver())


def prompt_for_missing_fields(missing_fields: list[str], lang: str) -> dict[str, str]:
    label = {
        "origin": _t(lang, "Origin"),
        "destination": _t(lang, "Destination"),
        "departure_time": _t(lang, "Departure time"),
        "fare": _t(lang, "Fare"),
    }
    out: dict[str, str] = {}
    for f in missing_fields:
        while True:
            val = input(f"{label.get(f, f)}: ").strip()
            if val:
                out[f] = val
                break
    return out


def run_cli():
    if not os.getenv("OPENAI_API_KEY"):
        print(_t("en", "warn_no_key"))

    app = build_app()
    thread_id = "cli-thread"
    cfg = {"configurable": {"thread_id": thread_id}}

    print(f"{_t('en', 'smartmove')} CLI (type 'exit' to quit)\n")
    while True:
        user_text = input(f"{_t('en', 'you')}: ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break

        state: SmartMoveState = {
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

        out = app.invoke(state, cfg)
        while "__interrupt__" in out:
            interrupt_payload = out["__interrupt__"][0].value
            lang = out.get("language") or detect_language(user_text)
            print(f"\n{_t(lang, 'smartmove')}: {interrupt_payload.get('question')}\n")
            missing = interrupt_payload.get("missing_fields") or []
            updates = prompt_for_missing_fields(list(missing), lang)
            out = app.invoke(Command(resume=updates), cfg)

        lang = out.get("language") or detect_language(user_text)
        print(f"\n{_t(lang, 'smartmove')}: {out.get('response')}\n")
        state_view = {k: v for k, v in out.items() if k != "messages"}
        print("=== State ===")
        print(state_view)
        print("=============\n")

