# SmartMove - Agentic Transportation Query System

SmartMove is an intelligent transportation assistance system built with LangGraph that uses LLM, tools, state management, and memory to handle transportation queries through a Neo4j knowledge graph.

## Architecture

The system follows a multi-agent architecture with the following flow:

```
User Query
    │
    ▼
Intent Detection Node
    │
 ┌───────────────┬───────────────┬──────────────┐
 │               │               │
 ▼               ▼               ▼
Greeting Node   Transport Node  Fallback Node
                    │
                    ▼
             Query Understanding
                    │
                    ▼
           Missing Info Validator
                    │
            ┌────YES─────┐
            │            │
            ▼            │
     Follow-up Question  │
            │            │
            ▼            │
        User Reply  ─────┘
            │
            ▼
        Cypher Generator
            │
            ▼
         Neo4j Query
            │
            ▼
      Response Formatter
            │
            ▼
          Final Answer
```

## Features

- **Intent Detection**: Automatically classifies user queries into greetings, transportation queries, or fallback
- **Query Understanding**: Extracts key information from natural language queries
- **Missing Information Validation**: Identifies and requests missing information needed for transportation queries
- **Cypher Query Generation**: Converts natural language to Neo4j Cypher queries
- **Neo4j Integration**: Executes queries against a Neo4j transportation knowledge graph
- **Memory Management**: Maintains conversation history using LangGraph's memory system
- **Response Formatting**: Formats database results into user-friendly responses

## Installation

1. Install dependencies:
```bash
pip install -e .
```

Or using uv:
```bash
uv sync
```

2. Set up environment variables:
Create a `.env` file in the project root:
```env
OPENAI_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.7

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password_here

MEMORY_TYPE=memory
```

## Usage

Run the main application:
```bash
python main.py
```

The system will start an interactive session where you can ask transportation-related questions.

### Example Queries

- Greetings: "Hello", "Hi there"
- Transportation: "How do I get from Paris to London?", "Find routes from station A to station B"
- The system will ask follow-up questions if information is missing

## Project Structure

```
SmartMove/
├── smartmove/
│   ├── __init__.py          # Package initialization
│   ├── state.py              # State schema definition
│   ├── agents.py             # Agent node implementations
│   ├── tools.py              # Tools (Neo4j, Cypher generation, validation)
│   ├── graph.py              # LangGraph graph builder
│   ├── utils.py              # Utility functions
│   └── config.py             # Configuration management
├── main.py                   # Main entry point
├── pyproject.toml            # Project dependencies
└── README.md                 # This file
```

## Components

### State Management
The `SmartMoveState` TypedDict manages the conversation state including:
- Messages history
- Detected intent
- Query understanding
- Missing information
- Cypher queries and results
- Final answers

### Agents
- **Intent Detection Node**: Classifies user queries
- **Greeting Node**: Handles greetings with SmartMove branding
- **Transport Node**: Entry point for transportation queries
- **Query Understanding Node**: Extracts information from queries
- **Missing Info Validator**: Validates query completeness
- **Follow-up Question Node**: Generates questions for missing info
- **User Reply Node**: Processes user responses
- **Cypher Generator Node**: Generates Neo4j queries
- **Neo4j Query Node**: Executes queries
- **Response Formatter Node**: Formats results
- **Fallback Node**: Handles non-transportation queries

### Tools
- `execute_cypher_query`: Executes Cypher queries against Neo4j
- `generate_cypher_query`: Converts natural language to Cypher
- `validate_transport_query`: Validates and extracts information from queries

## Memory

The system uses LangGraph's `MemorySaver` to maintain conversation history across interactions, allowing for context-aware responses.

## Requirements

- Python >= 3.13
- OpenAI API key
- Neo4j database (local or remote)
- LangGraph
- LangChain
- Neo4j Python driver

## License

[Add your license here]





