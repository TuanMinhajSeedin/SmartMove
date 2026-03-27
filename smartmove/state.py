"""State schema for SmartMove agentic system."""

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class SmartMoveState(TypedDict):
    """State schema for the SmartMove agent system.

    Conversation / graph fields (required by LangGraph):
        messages: List of messages in the conversation

    Structured transportation state (your requested view):
        user_query: Raw user query text
        intent: Detected intent (greeting, transport, fallback)
        origin: Origin location (may be None before collected)
        destination: Destination location (may be None before collected)
        departure_time: Departure date/time (may be None before collected)
        date: Travel date string (if separated from time)
        transport_type: Bus / train / etc. (optional)
        missing_fields: List of missing field names
    """

    # Conversation / graph-related field
    messages: Annotated[List[BaseMessage], add_messages]

    # Structured transportation state
    user_query: str
    intent: Optional[str]
    origin: Optional[str]
    destination: Optional[str]
    departure_time: Optional[str]
    date: Optional[str]
    transport_type: Optional[str]
    missing_fields: Optional[List[str]]

