"""Agent nodes for SmartMove agentic system."""

from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from smartmove.state import SmartMoveState
from smartmove.tools import (
    execute_cypher_query,
    generate_cypher_query,
    validate_transport_query,
)
from smartmove.config import LLM_MODEL, LLM_TEMPERATURE


def get_llm() -> ChatOpenAI:
    """Lazily create an LLM instance using configuration/env (.env)."""
    return ChatOpenAI(model=LLM_MODEL, temperature=LLM_TEMPERATURE)


def intent_detection_node(state: SmartMoveState) -> SmartMoveState:
    """Detect the intent of the user's query.
    
    Routes to:
    - greeting: If it's a greeting or casual message
    - transport: If it's a transportation-related query
    - fallback: For any other queries
    """
    # Get the last user message
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if not last_message or not isinstance(last_message, HumanMessage):
        return {**state, "intent": "fallback"}
    
    query = last_message.content
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an intent classifier for SmartMove transportation system.
        
        Classify the user's message into one of these categories:
        - "greeting": Greetings, hello, hi, casual conversation
        - "transport": Transportation queries, route planning, travel information
        - "fallback": Anything else that doesn't fit the above
        
        Respond with ONLY one word: greeting, transport, or fallback"""),
        ("human", "User message: {query}")
    ])
    
    chain = prompt | get_llm()
    response = chain.invoke({"query": query})
    intent = response.content.strip().lower()
    
    # Ensure valid intent
    if intent not in ["greeting", "transport", "fallback"]:
        intent = "fallback"
    
    return {
        **state,
        "intent": intent,
        "query": query
    }


def greeting_node(state: SmartMoveState) -> SmartMoveState:
    """Handle greeting messages with SmartMove welcome format."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are SmartMove, a professional transportation assistance system.
        
        Respond to greetings using the SmartMove welcome format.
        
        Strict rules:
        - Do NOT respond like a casual chatbot
        - Do NOT say things like "I'm doing well"
        - Do NOT answer personal questions
        - Always introduce the system name "SmartMove"
        - Keep the message short and professional
        - Respond in the SAME language as the user
        
        Welcome format example:
        Welcome to SmartMove! I'm here to help you with transportation queries. How can I assist you today?"""),
        ("human", "{query}")
    ])
    
    chain = prompt | get_llm()
    response = chain.invoke({"query": state.get("query", "")})
    
    greeting_response = response.content
    
    return {
        **state,
        "final_answer": greeting_response,
        "messages": state.get("messages", []) + [AIMessage(content=greeting_response)]
    }


def query_understanding_node(state: SmartMoveState) -> SmartMoveState:
    """Understand and process the transportation query."""
    query = state.get("query", "")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a query understanding agent for SmartMove.
        
        Analyze the transportation query and extract key information:
        - Origin and destination locations
        - Date/time requirements
        - Transport preferences
        - Number of passengers
        - Any special requirements
        
        Provide a structured understanding of the query."""),
        ("human", "Query: {query}")
    ])
    
    chain = prompt | get_llm()
    response = chain.invoke({"query": query})
    understood_query = response.content
    
    return {
        **state,
        "understood_query": understood_query
    }


def missing_info_validator_node(state: SmartMoveState) -> SmartMoveState:
    """Validate if the query has all necessary information."""
    query = state.get("understood_query") or state.get("query", "")
    
    # Use the validation tool
    validation_result = validate_transport_query.invoke(query)
    
    missing_info = validation_result.get("missing_fields", [])
    is_complete = validation_result.get("is_complete", False)
    
    return {
        **state,
        "missing_info": missing_info if not is_complete else []
    }


def follow_up_question_node(state: SmartMoveState) -> SmartMoveState:
    """Generate a follow-up question to get missing information."""
    query = state.get("understood_query") or state.get("query", "")
    missing_info = state.get("missing_info", [])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are SmartMove, a focused transportation AI assistant.

        Generate a direct follow-up question to obtain ONLY the missing transportation
        details from the user.

        Missing information: {missing_info}

        Style requirements:
        - Do NOT start with phrases like "Thank you for your inquiry".
        - Do NOT end with phrases like "Looking forward to your response".
        - No small talk, no extra politeness or chit-chat.
        - Ask as a real AI agent: short, clear, and strictly task-oriented.
        - Prefer a single, compact question (or a short numbered list) that
          asks exactly for the missing fields and nothing else.
        - Respond in the same language as the user's query."""),
        ("human", "Original query: {query}")
    ])
    
    chain = prompt | get_llm()
    response = chain.invoke({
        "query": query,
        "missing_info": ", ".join(missing_info)
    })
    
    follow_up = response.content
    
    return {
        **state,
        "follow_up_question": follow_up,
        "final_answer": follow_up,
        "messages": state.get("messages", []) + [AIMessage(content=follow_up)]
    }


def user_reply_node(state: SmartMoveState) -> SmartMoveState:
    """Process user's reply to follow-up question."""
    # Get the last user message (the reply)
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if last_message and isinstance(last_message, HumanMessage):
        user_reply = last_message.content
        
        # Merge the reply with the original query
        original_query = state.get("understood_query") or state.get("query", "")
        updated_query = f"{original_query}. Additional info: {user_reply}"
        
        return {
            **state,
            "user_reply": user_reply,
            "understood_query": updated_query,
            "missing_info": []  # Reset to re-validate
        }
    
    return state


def cypher_generator_node(state: SmartMoveState) -> SmartMoveState:
    """Generate Cypher query from the understood query."""
    query = state.get("understood_query") or state.get("query", "")
    
    # Use the Cypher generation tool
    cypher_query = generate_cypher_query.invoke(query)
    
    return {
        **state,
        "cypher_query": cypher_query
    }


def neo4j_query_node(state: SmartMoveState) -> SmartMoveState:
    """Execute the Cypher query against Neo4j."""
    cypher_query = state.get("cypher_query", "")
    
    if not cypher_query:
        return {
            **state,
            "neo4j_result": {"success": False, "error": "No Cypher query generated"}
        }
    
    # Execute the query
    result = execute_cypher_query.invoke(cypher_query)
    
    return {
        **state,
        "neo4j_result": result
    }


def response_formatter_node(state: SmartMoveState) -> SmartMoveState:
    """Format the Neo4j result into a user-friendly response."""
    query = state.get("query", "")
    neo4j_result = state.get("neo4j_result", {})
    
    if not neo4j_result.get("success"):
        error_msg = neo4j_result.get("error", "Unknown error occurred")
        formatted_response = f"I encountered an error while processing your query: {error_msg}. Please try rephrasing your question."
    else:
        data = neo4j_result.get("data", [])
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are SmartMove. Format the transportation query results
            into a clear, user-friendly response.
            
            Be professional, concise, and helpful.
            Include relevant details like routes, times, prices, etc.
            Respond in the same language as the user's query."""),
            ("human", """Original query: {query}
            
            Query results: {results}
            
            Format this into a helpful response for the user.""")
        ])
        
        chain = prompt | get_llm()
        response = chain.invoke({
            "query": query,
            "results": str(data)
        })
        formatted_response = response.content
    
    return {
        **state,
        "final_answer": formatted_response,
        "messages": state.get("messages", []) + [AIMessage(content=formatted_response)]
    }


def fallback_node(state: SmartMoveState) -> SmartMoveState:
    """Handle queries that don't fit into greeting or transport categories."""
    query = state.get("query", "")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are SmartMove, a STRICTLY transportation-only assistance system.

        The user's query does NOT appear to be about transportation (e.g. routes, stations,
        travel options, schedules, prices, transfers, or navigation).

        Very important behavioural rules:
        - You MUST NOT provide advice or help in any non-transportation domain
          (for example: cooking, health, finance, relationships, coding, etc.).
        - You MUST NOT suggest or describe how to do the non-transport activity itself.
        - You MAY ONLY mention transportation-related aspects (e.g. how to get to a place).
        - Always clearly state that SmartMove only supports transportation-related queries.
        - Politely ask the user to rephrase their request as a transportation question.
        - Keep the answer short, professional, and focused on transportation only.

        If there is NO clear transportation angle in the query, do NOT invent one.
        Simply say that SmartMove only supports transportation questions and invite
        the user to ask about routes, stations, or travel options instead."""),
        ("human", "User query: {query}")
    ])
    
    chain = prompt | get_llm()
    response = chain.invoke({"query": query})
    fallback_response = response.content
    
    return {
        **state,
        "final_answer": fallback_response,
        "messages": state.get("messages", []) + [AIMessage(content=fallback_response)]
    }


def should_continue_missing_info(state: SmartMoveState) -> Literal["follow_up", "continue"]:
    """Determine if we need to ask for missing info or continue."""
    missing_info = state.get("missing_info", [])
    if missing_info:
        return "follow_up"
    return "continue"


def transport_node(state: SmartMoveState) -> SmartMoveState:
    """Transport node - entry point for transport queries.
    
    This node just passes through to query_understanding.
    The actual flow is handled by the graph edges.
    """
    return state


def route_intent(state: SmartMoveState) -> Literal["greeting", "transport", "fallback"]:
    """Route based on detected intent."""
    intent = state.get("intent", "fallback")
    return intent  # type: ignore

