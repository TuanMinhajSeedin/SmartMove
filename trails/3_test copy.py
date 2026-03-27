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


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(model=OPENAI_MODEL, temperature=OPENAI_TEMPERATURE)


class SmartMoveState(TypedDict):
    messages: Annotated[list[Any], add_messages]

    user_query: str
    intent: str | None

    origin: str | None
    destination: str | None
    departure_time: str | None
    date: str | None
    transport_type: str | None

    missing_fields: list[str] | None

    cypher_query: str | None
    result: str | None
    response: str | None
    follow_up_question: str | None


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

    if not destination:
        to_match = re.search(
            r"(?:go|travel|reach|get)\s+to\s+([A-Za-z\s]+?)(?:$|\s+(?:on|at|by|for|after|before)\b)",
            text,
            re.IGNORECASE,
        )
        if to_match:
            destination = to_match.group(1).strip()

    if not destination:
        go_match = re.search(
            r"(?:go|get|travel|reach)\s+([A-Za-z\s]+?)(?:$|\s+(?:on|at|by|for|after|before)\b)",
            text,
            re.IGNORECASE,
        )
        if go_match:
            destination = go_match.group(1).strip()

    origin = _clean_place(origin)
    destination = _clean_place(destination)
    departure_time = normalize_datetime(text)

    return {
        "origin": origin,
        "destination": destination,
        "departure_time": departure_time,
        "date": departure_time,
        "transport_type": transport_type,
    }


def validate_mandatory_fields(state: SmartMoveState) -> list[str]:
    missing: list[str] = []
    if not state.get("origin"):
        missing.append("origin")
    if not state.get("destination"):
        missing.append("destination")
    if not state.get("departure_time"):
        missing.append("departure_time")
    return missing


def generate_cypher_for_transport(state: SmartMoveState) -> str:
    transport = state.get("transport_type") or "any"
    origin = state.get("origin") or "<origin>"
    destination = state.get("destination") or "<destination>"
    departure = state.get("departure_time") or "<departure_time>"

    return (
        "MATCH (o:Location {name: $origin})-[:CONNECTS]->(r:Route)-[:CONNECTS]->(d:Location {name: $destination}) "
        "WHERE ($transport = 'any' OR r.transport_type = $transport) "
        "RETURN o.name AS origin, d.name AS destination, r.transport_type AS transport_type, "
        "$departure AS departure_time, r.duration AS duration, r.price AS price"
    ).replace("$origin", f"'{origin}'").replace("$destination", f"'{destination}'").replace("$transport", f"'{transport}'").replace("$departure", f"'{departure}'")


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
    response = "Welcome to SmartMove. I can help with routes, schedules, and transport options."
    return {**state, "response": response, "messages": state.get("messages", []) + [AIMessage(content=response)]}


def fallback_node(state: SmartMoveState) -> SmartMoveState:
    response = "SmartMove supports transportation queries only. Please ask about routes, stations, or travel options."
    return {**state, "response": response, "messages": state.get("messages", []) + [AIMessage(content=response)]}


def query_understanding_node(state: SmartMoveState) -> SmartMoveState:
    extracted = extract_transport_fields(state.get("user_query") or "")

    merged = {
        "origin": state.get("origin") or extracted.get("origin"),
        "destination": state.get("destination") or extracted.get("destination"),
        "departure_time": state.get("departure_time") or extracted.get("departure_time"),
        "date": state.get("date") or extracted.get("date"),
        "transport_type": state.get("transport_type") or extracted.get("transport_type"),
    }
    return {**state, **merged}


def missing_info_validator_node(state: SmartMoveState) -> SmartMoveState:
    missing = validate_mandatory_fields(state)
    return {**state, "missing_fields": missing}


def _extract_missing_field_updates(state: SmartMoveState, missing: list[str], user_input: Any) -> dict[str, str | None]:
    if isinstance(user_input, dict):
        updates: dict[str, str | None] = {}
        for field in missing:
            if state.get(field):
                continue
            v = user_input.get(field)
            if isinstance(v, str) and v.strip():
                updates[field] = v.strip().lower() if field in {"origin", "destination"} else v.strip().lower()
        return updates

    user_text = str(user_input).strip()
    extracted = extract_transport_fields(user_text)
    updates2: dict[str, str | None] = {}

    for field in missing:
        if state.get(field):
            continue
        value = extracted.get(field)
        if not value:
            if field in {"origin", "destination"}:
                value = _clean_place(user_text)
            elif field == "departure_time":
                value = normalize_datetime(user_text) or user_text.strip().lower() or None
        if value:
            updates2[field] = value
    return updates2


def follow_up_question_node(state: SmartMoveState) -> SmartMoveState:
    missing = state.get("missing_fields") or []

    field_map = {"origin": "origin", "destination": "destination", "departure_time": "departure time"}
    missing_text = ", ".join(field_map.get(f, f) for f in missing)
    response = f"Please provide the following required details: {missing_text}."

    human_reply = interrupt({"kind": "follow_up_question", "question": response, "missing_fields": missing})
    updates = _extract_missing_field_updates(state, missing, human_reply)

    messages = state.get("messages", []) + [AIMessage(content=response)]
    if isinstance(human_reply, dict):
        messages = messages + [HumanMessage(content=str(human_reply))]
    else:
        messages = messages + [HumanMessage(content=str(human_reply).strip())]

    return {**state, **updates, "follow_up_question": response, "response": response, "messages": messages}


def cypher_generator_node(state: SmartMoveState) -> SmartMoveState:
    return {**state, "cypher_query": generate_cypher_for_transport(state)}


def neo4j_query_node(state: SmartMoveState) -> SmartMoveState:
    return {**state, "result": execute_neo4j_safe(state.get("cypher_query") or "")}


def response_formatter_node(state: SmartMoveState) -> SmartMoveState:
    query = state.get("user_query") or ""
    result = state.get("result") or "No result"

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are SmartMove response formatter.\n"
                "Create a concise transportation-focused answer from the result.\n"
                "No filler text.",
            ),
            ("human", "Query: {query}\nResult: {result}"),
        ]
    )

    response = (prompt | get_llm()).invoke({"query": query, "result": result}).content
    return {**state, "response": response, "messages": state.get("messages", []) + [AIMessage(content=response)]}


def route_intent(state: SmartMoveState) -> Literal["greeting", "transport", "fallback"]:
    return state.get("intent") or "fallback"


def route_missing_info(state: SmartMoveState) -> Literal["follow_up", "continue"]:
    return "follow_up" if (state.get("missing_fields") or []) else "continue"


def build_app():
    graph = StateGraph(SmartMoveState)
    graph.add_node("intent_detection", intent_detection_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("fallback", fallback_node)

    graph.add_node("query_understanding", query_understanding_node)
    graph.add_node("missing_info_validator", missing_info_validator_node)
    graph.add_node("follow_up_question", follow_up_question_node)
    graph.add_node("cypher_generator", cypher_generator_node)
    graph.add_node("neo4j_query", neo4j_query_node)
    graph.add_node("response_formatter", response_formatter_node)

    graph.add_edge(START, "intent_detection")
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


def _prompt_for_missing_fields(missing_fields: list[str]) -> dict[str, str]:
    label = {"origin": "Origin", "destination": "Destination", "departure_time": "Departure time"}
    out: dict[str, str] = {}

    for f in missing_fields:
        while True:
            val = input(f"{label.get(f, f)}: ").strip()
            if val:
                out[f] = val
                break
    return out


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Please set it in your .env file.")

    app = build_app()
    thread_id = "cli-thread"
    cfg = {"configurable": {"thread_id": thread_id}}

    print("SmartMove CLI (type 'exit' to quit)\n")

    while True:
        user_text = input("You: ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break

        state: SmartMoveState = {
            "messages": [HumanMessage(content=user_text)],
            "user_query": user_text,
            "intent": None,
            "origin": None,
            "destination": None,
            "departure_time": None,
            "date": None,
            "transport_type": None,
            "missing_fields": None,
            "cypher_query": None,
            "result": None,
            "response": None,
            "follow_up_question": None,
        }

        out = app.invoke(state, cfg)

        while "__interrupt__" in out:
            interrupt_payload = out["__interrupt__"][0].value
            print(f"\nSmartMove: {interrupt_payload.get('question')}\n")
            missing = interrupt_payload.get("missing_fields") or []
            updates = _prompt_for_missing_fields(list(missing))
            out = app.invoke(Command(resume=updates), cfg)

        print(f"\nSmartMove: {out.get('response')}\n")


if __name__ == "__main__":
    main()

