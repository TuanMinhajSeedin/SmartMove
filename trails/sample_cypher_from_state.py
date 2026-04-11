"""
Run Cypher generation from a fixed transport state using the SmartMove
cypher_generator_node (LLM tool: smartmove.tools.generate_cypher_query).

Requires OPENAI_API_KEY in the environment (see project .env).
"""

from __future__ import annotations

from pprint import pprint

from dotenv import load_dotenv

from smartmove.agents import cypher_generator_node

load_dotenv()

# Sample state matching your transport extraction output (valid Python dict).
SAMPLE_STATE: dict = {
    "user_query": "I need to go on a trip.",
    "user_query_original": "මට ගමනක් යෑමට අවශ්‍යයි.",
    "language": "si",
    "intent": "transport",
    "origin": "kandy",
    "destination": "colombo",
    "departure_time": "after 5n",
    "date": None,
    "transport_type": None,
    "fare": "Receiving",
}


def build_understood_query(state: dict) -> str:
    """Turn structured fields into one NL string for the Cypher generator."""
    date = state.get("date")
    ttype = state.get("transport_type")
    return (
        "Transportation route search. "
        f"User intent: {state.get('intent')}. "
        f"English query: {state.get('user_query', '')}. "
        f"Original (Sinhala): {state.get('user_query_original', '')}. "
        f"Origin: {state.get('origin')}. "
        f"Destination: {state.get('destination')}. "
        f"Departure time preference: {state.get('departure_time')}. "
        f"Travel date: {date if date is not None else 'not specified'}. "
        f"Transport type: {ttype if ttype is not None else 'any'}. "
        f"Fare / pricing preference: {state.get('fare')}."
    )


def main() -> None:
    understood = build_understood_query(SAMPLE_STATE)
    # cypher_generator_node uses understood_query, else query (see smartmove.agents)
    state_in = {
        **SAMPLE_STATE,
        "understood_query": understood,
    }
    out = cypher_generator_node(state_in)
    print("understood_query:\n", understood, "\n")
    print("Generated Cypher:\n", out.get("cypher_query"))
    print("\nFull output keys:", sorted(out.keys()))
    pprint({k: out[k] for k in ("cypher_query", "understood_query") if k in out})


if __name__ == "__main__":
    main()
