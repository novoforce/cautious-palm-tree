# app/services/email_agent/agent.py
import asyncio
import uuid
import os
from typing import Dict, Any

from google.adk.agents import LlmAgent
from google.genai.types import Content, Part
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools.application_integration_tool.application_integration_toolset import ApplicationIntegrationToolset

# Import our centralized settings
from app.core.config import settings

# --- Constants ---
APP_NAME = "email_app"
USER_ID = "dev_user_01"

# --- Tool and Agent Setup (Instantiated once on import) ---

# 1. Read the service account key from the path defined in config.py
sa_key_path = settings.INTEGRATION_CONNECTOR_SERVICE_ACCOUNT_KEY_PATH
if not os.path.exists(sa_key_path):
    raise FileNotFoundError(
        f"Service account key not found at path: {sa_key_path}. "
        "Please check your INTEGRATION_CONNECTOR_SERVICE_ACCOUNT_KEY_PATH in .env"
    )

with open(sa_key_path, 'r') as f:
    sa_key_string = f.read()

# 2. Define the Application Integration Tool
email_tool = ApplicationIntegrationToolset(
    # Use the project ID from our settings
    project=settings.GOOGLE_CLOUD_PROJECT_ID,
    location=settings.INTEGRATION_CONNECTOR_LOCATION,
    integration="sendEmailAshish",
    triggers=["api_trigger/sendEmailAshish_API_1"],
    service_account_json=sa_key_string,
    tool_name_prefix="email_sender",
    tool_instructions="Use this tool to send an email. You must provide the recipient's email, the subject, and the body of the message.",
)

# 3. Define the LlmAgent that uses the tool
email_agent = LlmAgent(
    name='email_agent',
    # Use the model from our settings
    model=settings.EMAIL_AGENT_GEMINI_MODEL,
    instruction=(
        "You are an agent that can send emails. When a user asks to send an email, "
        "use the `email_sender` tool. Infer the recipient, subject, and body from the user's request. "
        "After successfully using the tool, confirm to the user that the email has been sent."
    ),
    tools=[email_tool],
    output_key="email_agent_response" # Giving a clear output key
)

# 4. Set up the session service
_session_service = InMemorySessionService()


async def call_email_agent(user_query: str) -> Dict[str, Any]:
    """
    Executes the email agent to process a user's request to send an email.

    This agent uses a tool to interact with Google Cloud Application Integration.
    It requires a specific user query that contains information for the email.

    Example Query: "Please send an email to student@university.edu with the subject 'Project Update' and the body 'The report is attached.'"

    Args:
        user_query (str): The user's instruction to send an email.

    Returns:
        dict: A dictionary containing the agent's final confirmation or an error.
    """
    try:
        current_session_id = str(uuid.uuid4())
        print(f"▶️  Running EmailAgent for query: '{user_query[:50]}...'")
        await _session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        runner = Runner(
            agent=email_agent,
            app_name=APP_NAME,
            session_service=_session_service,
        )

        initial_message = Content(role="user", parts=[Part(text=user_query)])

        # The loop runs the agent, which will internally decide to use the email_tool
        async for _ in runner.run_async(
            user_id=USER_ID, session_id=current_session_id, new_message=initial_message
        ):
            pass

        session_state_data = await _session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        # The final response from the agent after it has used the tool
        final_response = session_state_data.state.get("email_agent_response")
        
        # You can also inspect the tool calls if needed for debugging
        # print("Full session state:", session_state_data.state)

        print("✅ EmailAgent completed successfully.")
        return {
            "response": (
                final_response if final_response else "No confirmation response was generated."
            )
        }

    except Exception as e:
        import traceback

        print(f"❌ EmailAgent failed with an error: {e}")
        traceback.print_exc()
        return {"error": str(e), "response": "Agent execution failed."}


# --- Example Usage ---
async def main():
    """Main function to demonstrate running the email agent."""
    print("--- Running EmailAgent ---")

    # The user input MUST be specific enough for the agent to use the tool.
    user_input = "Could you send an email to test@example.com with the subject 'Hello from the ADK Agent' and the body 'This is a test message sent via Application Integration.'?"
    result = await call_email_agent(user_input)

    if result.get("error"):
        print(f"\nError: {result['error']}")
    else:
        print(f"\nUser Query: {user_input}")
        print(f"Agent Response: {result['response']}")


if __name__ == "__main__":
    asyncio.run(main())