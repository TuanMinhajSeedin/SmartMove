"""Tools for SmartMove agentic system."""

from typing import Optional, Dict, Any
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import os
from neo4j import GraphDatabase


# Neo4j connection (will be initialized with environment variables)
_neo4j_driver: Optional[Any] = None


def get_neo4j_driver():
    """Get or create Neo4j driver connection."""
    global _neo4j_driver
    if _neo4j_driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        _neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
    return _neo4j_driver


@tool
def execute_cypher_query(cypher_query: str) -> Dict[str, Any]:
    """Execute a Cypher query against Neo4j database.
    
    Args:
        cypher_query: The Cypher query string to execute
        
    Returns:
        Dictionary containing query results or error information
    """
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            result = session.run(cypher_query)
            records = [dict(record) for record in result]
            return {
                "success": True,
                "data": records,
                "count": len(records)
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


@tool
def generate_cypher_query(
    query: str,
    schema_info: Optional[str] = None
) -> str:
    """Generate a Cypher query from natural language query.
    
    This tool uses an LLM to convert natural language transportation queries
    into valid Cypher queries for Neo4j.
    
    Args:
        query: Natural language query about transportation
        schema_info: Optional schema information about the Neo4j database
        
    Returns:
        Generated Cypher query string
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    schema = schema_info or """
    Common Neo4j schema for transportation:
    - Nodes: Location, Route, Transport, Station, Stop
    - Relationships: CONNECTS, SERVES, OPERATES, LOCATED_AT
    - Properties: name, distance, duration, price, capacity, etc.
    """
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a Cypher query generator for a transportation database.
        
        Database Schema:
        {schema}
        
        Generate valid Cypher queries that:
        1. Match the user's intent
        2. Use proper Neo4j syntax
        3. Return relevant transportation information
        
        Return ONLY the Cypher query, no explanations."""),
        ("human", "User query: {query}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"query": query, "schema": schema})
    return response.content.strip()


@tool
def validate_transport_query(query: str) -> Dict[str, Any]:
    """Validate a transportation query and identify missing information.
    
    Args:
        query: The user's transportation query
        
    Returns:
        Dictionary with validation results and missing fields
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a query validator for transportation queries.
        
        Your job is to check if the query contains ALL of the following:
        - Origin location      (required)
        - Destination location (required)
        - Departure date/time  (required)
        
        Number of passengers is OPTIONAL and must NOT be treated as required.
        
        Return a JSON object with:
        {{
            "is_complete": boolean,
            "missing_fields": ["field1", "field2"],
            "extracted_info": {{
                "origin": "...",
                "destination": "...",
                "date": "...",
                "transport_type": "...",
                "passengers": "..."
            }}
        }}"""),
        ("human", "Query: {query}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"query": query})
    
    # Parse JSON response
    import json
    try:
        result = json.loads(response.content)
        # Normalize and enforce that ONLY origin, destination, departure_time are mandatory
        missing = [f.lower() for f in result.get("missing_fields", [])]
        normalized = []
        for f in missing:
            if "origin" in f:
                normalized.append("origin")
            elif "destination" in f:
                normalized.append("destination")
            elif f in {"date", "time", "date/time", "departure", "departure_time"}:
                normalized.append("departure_time")
        # Remove duplicates while preserving order
        seen = set()
        filtered_missing = []
        for f in normalized:
            if f not in seen:
                seen.add(f)
                filtered_missing.append(f)
        result["missing_fields"] = filtered_missing
        # Complete only when all three mandatory fields are present
        result["is_complete"] = len(filtered_missing) == 0
        return result
    except:
        return {
            "is_complete": False,
            "missing_fields": ["origin", "destination"],
            "extracted_info": {}
        }


