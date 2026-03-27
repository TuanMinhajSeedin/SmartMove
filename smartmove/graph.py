"""LangGraph graph builder for SmartMove agentic system."""

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from smartmove.state import SmartMoveState
from smartmove.agents import (
    intent_detection_node,
    greeting_node,
    transport_node,
    fallback_node,
    route_intent,
    should_continue_missing_info,
    query_understanding_node,
    missing_info_validator_node,
    follow_up_question_node,
    user_reply_node,
    cypher_generator_node,
    neo4j_query_node,
    response_formatter_node,
)


def build_smartmove_graph() -> StateGraph:
    """Build the SmartMove agentic graph with all nodes and routing.
    
    Graph structure:
    - Entry → Intent Detection
    - Intent Detection → (Greeting | Transport | Fallback)
    - Transport → Query Understanding → Missing Info Validator
    - Missing Info Validator → (Follow-up Question → END) | Continue
    - User Reply → Missing Info Validator (when continuing via main.py)
    - Continue → Cypher Generator → Neo4j Query → Response Formatter → Final Answer
    
    Note: User reply handling is managed in main.py by re-invoking the graph
    with updated state that routes to user_reply node.
    """
    # Create the graph
    workflow = StateGraph(SmartMoveState)
    
    # Add nodes
    workflow.add_node("intent_detection", intent_detection_node)
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("transport", transport_node)
    workflow.add_node("fallback", fallback_node)
    
    # Add transport sub-flow nodes
    workflow.add_node("query_understanding", query_understanding_node)
    workflow.add_node("missing_info_validator", missing_info_validator_node)
    workflow.add_node("follow_up_question", follow_up_question_node)
    workflow.add_node("user_reply", user_reply_node)
    workflow.add_node("cypher_generator", cypher_generator_node)
    workflow.add_node("neo4j_query", neo4j_query_node)
    workflow.add_node("response_formatter", response_formatter_node)
    
    # Set entry point (default to intent_detection)
    # For user_reply continuation, main.py will invoke with state that has user_reply set
    workflow.set_entry_point("intent_detection")
    
    # Route from intent detection
    workflow.add_conditional_edges(
        "intent_detection",
        route_intent,
        {
            "greeting": "greeting",
            "transport": "transport",
            "fallback": "fallback"
        }
    )
    
    # Terminal nodes
    workflow.add_edge("greeting", END)
    workflow.add_edge("fallback", END)
    
    # Transport flow
    workflow.add_edge("transport", "query_understanding")
    workflow.add_edge("query_understanding", "missing_info_validator")
    
    # Conditional routing from missing info validator
    workflow.add_conditional_edges(
        "missing_info_validator",
        should_continue_missing_info,
        {
            "follow_up": "follow_up_question",
            "continue": "cypher_generator"
        }
    )
    
    # Follow-up loop
    # Note: follow_up_question ends to wait for user input
    # The main.py will handle continuing with user_reply
    workflow.add_edge("follow_up_question", END)
    workflow.add_edge("user_reply", "missing_info_validator")  # Re-validate after user reply
    
    # Continue with query execution
    workflow.add_edge("cypher_generator", "neo4j_query")
    workflow.add_edge("neo4j_query", "response_formatter")
    workflow.add_edge("response_formatter", END)
    
    return workflow


def create_smartmove_agent():
    """Create a SmartMove agent with memory."""
    graph = build_smartmove_graph()
    
    # Add memory checkpoint
    memory = MemorySaver()
    
    # Compile the graph with memory
    app = graph.compile(checkpointer=memory)
    
    return app



