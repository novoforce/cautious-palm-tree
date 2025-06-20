# from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
# from google.adk.agents.callback_context import CallbackContext
# from google.cloud import bigquery
# from google.cloud.exceptions import NotFound, GoogleCloudError
# from app.core.config import settings
# import logging
# import traceback
# import os
# from google.genai import types
# from google.adk.models import Gemini

# general_greeting_agent = LlmAgent(
#     name="general_greeting_agent",
#     model="gemini-2.0-flash-001", #"gemini-2.5-flash-preview-04-17",
#     description=(
#         "Agent to answer questions relating to user general query"
#     ),
#     instruction=(
#         """You are a helpful agent who can answer user questions and have a great open conversation.
#         You can speak in English, Hindi, or any other language."""
#     ),
    
# )

import asyncio
import uuid
import os
from typing import Dict, Any

from google.adk.agents import LlmAgent
from google.genai.types import Content, Part
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv

# --- Constants ---
# It's good practice to define these for clarity and reusability.
APP_NAME = "greeting_app"
USER_ID = "dev_user_01"
GEMINI_MODEL = "gemini-2.0-flash-001"

# --- Agent and Session Service Setup (Instantiated once on import) ---

general_greeting_agent = LlmAgent(
    name="general_greeting_agent",
    model=GEMINI_MODEL,
    instruction=(
        """You are a friendly and helpful agent who engages in meaningful conversations with users, answering their questions and making them feel valued.
        You can speak in English, Hindi, or any other language as per the user's preference."""
    ),
    description=(
        "An engaging agent to answer user queries and foster meaningful connections."
    ),
    output_key="greeting_response",  # <-- IMPORTANT: Key to retrieve the output
)

# A simple in-memory session service, same as your reference.
# This is suitable for development and simple applications.
_session_service = InMemorySessionService()


async def execute_greeting(user_query: str) -> Dict[str, Any]:
    """
    Executes the greeting agent to get a conversational response.

    This function sets up a session, runs the LlmAgent with the user's query,
    and retrieves the generated response. It mirrors the structure of your
    working reference code.

    Args:
        user_query (str): The user's message or question.
                          Example: "Hello, how are you today?"

    Returns:
        dict: A dictionary containing the agent's response or an error message.
            - 'response' (str): The conversational reply from the agent.
            - 'error' (str, optional): An error message if the execution fails.
    """
    # Load environment variables (e.g., GOOGLE_API_KEY) from a .env file
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        return {"error": "GOOGLE_API_KEY environment variable not found."}

    try:
        # Step 1: Create a unique session for this interaction.
        # This keeps conversations isolated.
        current_session_id = str(uuid.uuid4())
        print(f"▶️  Running Greeting Agent for query: '{user_query[:50]}...'")
        await _session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        # Step 2: Instantiate the Runner.
        # The runner orchestrates the execution of the agent within the session.
        runner = Runner(
            agent=general_greeting_agent,
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

        print("✅ Greeting Agent completed successfully.")
        return {
            "response": final_response if final_response else "No response was generated."
        }

    except Exception as e:
        import traceback
        print(f"❌ Greeting Agent failed with an error: {e}")
        traceback.print_exc()
        return {"error": str(e), "response": "Agent execution failed."}


# --- Example Usage ---
async def main():
    """Main function to demonstrate running the greeting agent."""
    print("--- Running Greeting Agent ---")
    
    # Make sure you have a .env file with your GOOGLE_API_KEY
    # Or that the environment variable is set.
    # .env file content:
    # GOOGLE_API_KEY="your_api_key_here"

    user_input = "Hello there! How does quantum computing work in simple terms?"
    result = await execute_greeting(user_input)

    if result.get("error"):
        print(f"\nError: {result['error']}")
    else:
        print(f"\nUser Query: {user_input}")
        print(f"Agent Response: {result['response']}")

if __name__ == "__main__":
    # This allows you to run the script directly to test the function.
    asyncio.run(main())