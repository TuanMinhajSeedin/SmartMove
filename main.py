"""Main entry point for SmartMove agentic system."""

import os
from pprint import pprint
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from smartmove.graph import create_smartmove_agent
from smartmove.state import SmartMoveState
from smartmove.utils import continue_with_user_reply, should_wait_for_reply

# Load environment variables
load_dotenv()


def main():
    """Main function to run SmartMove agentic system."""
    print("Initializing SmartMove agentic system...")
    
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Please set it in your .env file.")
    
    # Create the agent with memory
    agent = create_smartmove_agent()
    
    print("SmartMove is ready! Type 'exit' to quit.\n")
    
    # Initialize conversation thread
    thread_id = "default"
    config = {"configurable": {"thread_id": thread_id}}
    
    # Interactive loop
    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()
            
            if user_input.lower() in ["exit", "quit", "bye"]:
                print("Goodbye! Thank you for using SmartMove.")
                break
            
            if not user_input:
                continue
            
            # Create initial state
            initial_state: SmartMoveState = {
                "messages": [HumanMessage(content=user_input)],
                "intent": None,
                "query": user_input,
                "understood_query": None,
                "missing_info": [],
                "follow_up_question": None,
                "user_reply": None,
                "cypher_query": None,
                "neo4j_result": None,
                "final_answer": None,
                "conversation_history": []
            }
            
            # Invoke the agent
            result = agent.invoke(initial_state, config)
            
            # Display the response
            if result.get("final_answer"):
                print(f"\nSmartMove: {result['final_answer']}\n")
            else:
                # Get the last AI message if no final_answer
                messages = result.get("messages", [])
                if messages:
                    last_message = messages[-1]
                    if hasattr(last_message, "content"):
                        print(f"\nSmartMove: {last_message.content}\n")

            # Show current state after initial reply
            print("=== SmartMove state ===")
            pprint(result)
            print("=======================\n")
            
            # Check if we need to wait for user reply (follow-up question)
            while should_wait_for_reply(result):
                # Wait for user reply and continue
                user_reply = input("You: ").strip()
                if not user_reply:
                    continue
                
                # Continue the graph with user reply
                result = continue_with_user_reply(agent, result, user_reply, config)
                
                # Display the response
                if result.get("final_answer"):
                    print(f"\nSmartMove: {result['final_answer']}\n")

                # Show updated state after each follow-up answer
                print("=== SmartMove state ===")
                pprint(result)
                print("=======================\n")
        
        except KeyboardInterrupt:
            print("\n\nGoodbye! Thank you for using SmartMove.")
            break
        except Exception as e:
            print(f"\nError: {e}\n")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
