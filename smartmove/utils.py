"""Utility functions for SmartMove agentic system."""

from typing import Optional
from langchain_core.messages import HumanMessage
from smartmove.state import SmartMoveState
from smartmove.graph import create_smartmove_agent


def continue_with_user_reply(
    agent,
    current_state: SmartMoveState,
    user_reply: str,
    config: dict
) -> SmartMoveState:
    """Continue the graph execution with user's reply to follow-up question.
    
    This function manually processes the user_reply node and then continues
    the graph flow by invoking the missing_info_validator node.
    
    Args:
        agent: The compiled LangGraph agent
        current_state: Current state from previous execution
        user_reply: User's reply to the follow-up question
        config: Configuration for the agent (thread_id, etc.)
        
    Returns:
        Updated state after processing user reply
    """
    from smartmove.agents import user_reply_node, missing_info_validator_node, should_continue_missing_info
    
    # Add user reply to messages and state
    updated_state: SmartMoveState = {
        **current_state,
        "messages": current_state["messages"] + [HumanMessage(content=user_reply)],
        "user_reply": user_reply,
    }
    
    # Process user reply node
    updated_state = user_reply_node(updated_state)
    
    # Continue with missing info validator
    updated_state = missing_info_validator_node(updated_state)
    
    # Check if we need to continue or ask more questions
    if should_continue_missing_info(updated_state) == "continue":
        # Continue with the rest of the flow
        from smartmove.agents import (
            cypher_generator_node,
            neo4j_query_node,
            response_formatter_node
        )
        updated_state = cypher_generator_node(updated_state)
        updated_state = neo4j_query_node(updated_state)
        updated_state = response_formatter_node(updated_state)
    else:
        # Need to ask another follow-up question
        from smartmove.agents import follow_up_question_node
        updated_state = follow_up_question_node(updated_state)
    
    return updated_state


def should_wait_for_reply(state: SmartMoveState) -> bool:
    """Check if we should wait for user reply.
    
    Args:
        state: Current state
        
    Returns:
        True if we need to wait for user reply, False otherwise
    """
    return (
        state.get("follow_up_question") is not None and
        len(state.get("missing_info", [])) > 0 and
        state.get("user_reply") is None
    )

