import asyncio
import uuid
import os
from typing import Any, Optional

from google.adk.agents import Agent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.tools import LongRunningFunctionTool
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from dotenv import load_dotenv
from google.adk.tools.agent_tool import AgentTool
# --- Constants ---
APP_NAME = "human_in_the_loop_app"
USER_ID = "dev_user_02"
# Make sure to use a valid model that supports function calling.
GEMINI_MODEL = "gemini-2.0-flash-001" # Updated model for better function calling support

# --- Tool Functions ---
def ask_for_approval(
    purpose: str, amount: float
) -> dict[str, Any]:
    """Ask for approval for the reimbursement. This simulates creating a ticket."""
    print(f"--- TOOL: ask_for_approval called for ${amount} ---")
    # In a real app, this would create a ticket, send a notification, etc.
    return {'status': 'pending', 'approver': 'Sean Zhou', 'purpose' : purpose, 'amount': amount, 'ticket-id': f'approval-ticket-{uuid.uuid4()}'}

def reimburse(purpose: str, amount: float) -> dict[str, Any]:
    """Reimburse the amount of money to the employee."""
    print(f"--- TOOL: reimburse called for ${amount} ---")
    # In a real app, this would trigger a payment process.
    return {'status': 'ok'}

# --- Helper Functions to Parse Events ---
def get_long_running_function_call(event: Event) -> Optional[genai_types.FunctionCall]:
    """Get the long running function call from an event, if it exists."""
    if not (event.long_running_tool_ids and event.content and event.content.parts):
        return None
    for part in event.content.parts:
        if (
            part.function_call
            and part.function_call.id in event.long_running_tool_ids
        ):
            return part.function_call
    return None

def get_function_response(event: Event, function_call_id: str) -> Optional[genai_types.FunctionResponse]:
    """Get the function response for a specific function call ID from an event."""
    if not (event.content and event.content.parts):
        return None
    for part in event.content.parts:
        if (
            part.function_response
            and part.function_response.id == function_call_id
        ):
            return part.function_response
    return None

# --- Agent and Session Service Setup (Instantiated once on import) ---

# Wrap the long-running function with the ADK Tool
_long_running_tool = LongRunningFunctionTool(func=ask_for_approval)

# The Agent that uses the tools
_reimbursement_agent = Agent(
    model=GEMINI_MODEL,
    name='reimbursement_agent',
    instruction="""
      You are an agent whose job is to handle the reimbursement process for
      the employees. If the amount is less than $100, you will automatically
      approve the reimbursement by calling the reimburse() tool directly.

      If the amount is greater than or equal to $100, you will
      ask for approval from the manager by calling the ask_for_approval() tool.
      If the manager approves (simulated by a user message), you will then
      call the reimburse() tool. If the manager rejects, you will inform the
      employee of the rejection.
    """,
    tools=[reimburse, _long_running_tool]
)

# Session Service
_session_service = InMemorySessionService()

# --- Main Asynchronous Logic ---

async def _run_reimbursement_flow_async(query: str):
    """Internal async function to run the agent reimbursement flow."""
    # 1. SETUP: Create a unique session for this run
    current_session_id = str(uuid.uuid4())
    await _session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )

    runner = Runner(
        agent=_reimbursement_agent,
        app_name=APP_NAME,
        session_service=_session_service
    )

    # 2. INITIAL CALL: Send the user's query to the agent
    print("\n▶️  Running agent with initial query...")
    initial_message = genai_types.Content(role='user', parts=[genai_types.Part(text=query)])

    long_running_function_call = None
    async for event in runner.run_async(
        user_id=USER_ID, session_id=current_session_id, new_message=initial_message
    ):
        if text := "".join(part.text or "" for part in event.content.parts if part.text):
            print(f"[{event.author}]: {text}")

        # Check if the agent requested a long-running operation (approval)
        if not long_running_function_call:
            long_running_function_call = get_long_running_function_call(event)

    # 3. HUMAN-IN-THE-LOOP: If approval was requested, simulate the approval
    if long_running_function_call:
        print("\n▶️  Approval required. Simulating manager approval...")
        # In a real app, you would wait for an external event (e.g., a webhook).
        # Here, we create a response message as if the manager approved.
        approval_response_part = genai_types.Part(
            function_response=genai_types.FunctionResponse(
                id=long_running_function_call.id,
                name=long_running_function_call.name,
                response={'status': 'approved'}
            )
        )
        approval_message = genai_types.Content(parts=[approval_response_part], role='user')

        # 4. FINAL CALL: Send the approval back to the agent to complete the flow
        print("▶️  Sending approval back to agent...")
        async for event in runner.run_async(
          user_id=USER_ID, session_id=current_session_id, new_message=approval_message
        ):
            if text := "".join(part.text or "" for part in event.content.parts if part.text):
                print(f"[{event.author}]: {text}")

    print("✅ Flow completed.")


# --- Synchronous Wrapper Entrypoint ---

def execute_reimbursement_request(user_query: str):
    """
    Executes the reimbursement request flow.

    This is a synchronous wrapper that handles the async execution of the ADK agent.
    """
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ ERROR: GOOGLE_API_KEY environment variable not found.")
        return

    try:
        print(f"--- Starting New Request: '{user_query}' ---")
        asyncio.run(_run_reimbursement_flow_async(user_query))
        print("--- Request Finished ---\n")
    except Exception as e:
        print(f"❌ Pipeline failed with an error: {e}")

# --- Example Usage ---

if __name__ == "__main__":
    # Case 1: Reimbursement that doesn't require approval
    execute_reimbursement_request("Please reimburse $50 for my lunch.")

    # Case 2: Reimbursement that requires approval
    execute_reimbursement_request("Please reimburse $200 for my flight tickets.")