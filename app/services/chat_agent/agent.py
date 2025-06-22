# app/services/greeting_agent/agent.py
import asyncio
import uuid
import os
from typing import Dict, Any

from google.adk.agents import LlmAgent
from google.genai.types import Content, Part
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv
from app.core.config import settings
from .prompt import INSTRUCTIONS, DESCRIPTION

# --- Constants ---
APP_NAME = "greeting_app"
USER_ID = "dev_user_01"

# --- Agent and Session Service Setup (Instantiated once on import) ---
chat_agent = LlmAgent(
    name="chat_agent",
    model=settings.GREETING_AGENT_GEMINI_MODEL,
    instruction=INSTRUCTIONS,
    description=DESCRIPTION,
    output_key="greeting_response",
)

_session_service = InMemorySessionService()


async def call_chat_agent(user_query: str) -> Dict[str, Any]:
    """
    The chat agent is designed to handle user greetings and engage in general conversation.

    Capabilities:
    - Understand and respond to user greetings.
    - Provide information and engage in casual conversation.
    - Use a friendly and engaging tone.
    - Responses are clear, concise, and relevant to the user's query.
    - Maintain a conversational flow that encourages further interaction.
    
    Example Query: "Hello, how are you today?"

    Args:
        user_query (str): The user's message or question.

    Returns:
        dict: A dictionary containing the agent's response or an error message.
            - 'response' (str): The conversational reply from the agent.
            - 'error' (str, optional): An error message if the execution fails.
    """
    try:
        # Step 1: Create a unique session for this interaction.
        # This keeps conversations isolated.
        current_session_id = str(uuid.uuid4())
        print(f"▶️  Running ChatAgent for query: '{user_query[:50]}...'")
        await _session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        # Step 2: Instantiate the Runner.
        # The runner orchestrates the execution of the agent within the session.
        runner = Runner(
            agent=chat_agent,
            app_name=APP_NAME,
            session_service=_session_service,
        )

        # Step 3: Format the input for the agent.
        # The ADK standard is to use Content/Part objects.
        initial_message = Content(role="user", parts=[Part(text=user_query)])

        # Step 4: Execute the agent asynchronously.
        # We loop through the runner's async generator to let it run to completion.
        async for _ in runner.run_async(
            user_id=USER_ID, session_id=current_session_id, new_message=initial_message
        ):
            pass  # The loop consumes the async generator until the agent is done.

        # Step 5: Retrieve the final state of the session.
        session_state_data = await _session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        # Step 6: Extract the output from the session state.
        # We use the 'output_key' ("greeting_response") we defined in the LlmAgent.
        final_response = session_state_data.state.get("greeting_response")

        print("✅ ChatAgent completed successfully.")
        return {
            "response": (
                final_response if final_response else "No response was generated."
            )
        }

    except Exception as e:
        import traceback

        print(f"❌ ChatAgent failed with an error: {e}")
        traceback.print_exc()
        return {"error": str(e), "response": "Agent execution failed."}


# --- Example Usage ---
async def main():
    """Main function to demonstrate running the chat agent."""
    print("--- Running ChatAgent ---")

    user_input = "Hello there! How are you doing today?"
    result = await call_chat_agent(user_input)

    if result.get("error"):
        print(f"\nError: {result['error']}")
    else:
        print(f"\nUser Query: {user_input}")
        print(f"Agent Response: {result['response']}")


if __name__ == "__main__":
    # This allows you to run the script directly to test the function.
    asyncio.run(main())
