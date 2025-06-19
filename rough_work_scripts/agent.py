import asyncio
import os
import uuid
from typing import AsyncGenerator

from google.genai.types import Content, Part
from google.adk.agents.llm_agent import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
# FIX: Explicitly wrap the streaming tool with FunctionTool
from google.adk.tools.function_tool import FunctionTool
import google.generativeai as genai
from dotenv import load_dotenv

# --- Constants & Setup ---
APP_NAME = "stock_monitor_app"
USER_ID = "dev_user_stocks"
GEMINI_MODEL = "gemini-2.0-flash-001"

# --- Streaming Tool Functions ---

async def monitor_stock_price(stock_symbol: str) -> AsyncGenerator[str, None]:
  """This function will monitor the price for the given stock_symbol in a continuous, streaming and asynchronously way."""
  print(f"--- TOOL: Started monitoring stock price for {stock_symbol}! ---")
  for price in [300, 400, 900, 500]:
      await asyncio.sleep(2)
      price_alert = f"Price alert for {stock_symbol}: ${price}"
      yield price_alert
  print(f"--- TOOL: Finished monitoring {stock_symbol}. ---")


def stop_streaming(function_name: str):
  """Stop the streaming
  Args:
    function_name: The name of the streaming function to stop.
  """
  print(f"--- AGENT ACTION: Attempting to stop streaming for '{function_name}' ---")
  pass

# --- Agent and Session Service Setup ---

_stock_agent = Agent(
    model=GEMINI_MODEL,
    name="stock_monitoring_agent",
    instruction="""
      You are a stock monitoring agent.
      When a user asks to monitor a stock, use the monitor_stock_price tool.
      When the tool provides a price alert, you must relay that information clearly to the user.
      When a user asks to stop, use the stop_streaming tool.
    """,
    tools=[
        # FIX: Explicitly wrap the streaming tool with FunctionTool.
        # This prevents the framework from trying to pickle the generator object.
        FunctionTool(monitor_stock_price),
        FunctionTool(stop_streaming),
    ],
)

_session_service = InMemorySessionService()

# --- Main Asynchronous Logic ---

async def _run_stock_monitoring_async(query: str):
    """Runs the agent and processes all events from a single run_async call."""
    current_session_id = str(uuid.uuid4())
    await _session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )
    runner = Runner(agent=_stock_agent, app_name=APP_NAME, session_service=_session_service)

    print(f"\n[USER]: {query}")

    initial_message = Content(role="user", parts=[Part(text=query)])

    async for event in runner.run_async(
        user_id=USER_ID, session_id=current_session_id, new_message=initial_message
    ):
        if event.content and event.content.parts:
            # The warning you saw is because some parts are function calls.
            # We only want to print the text parts for the user.
            if text := "".join(p.text or "" for p in event.content.parts if p.text):
                print(f"[{event.author.upper()}]: {text}")

    print("\n--- Flow finished ---")


# --- Synchronous Wrapper Entrypoint ---

def execute_stock_monitoring(user_query: str):
    """Synchronous wrapper to execute the stock monitoring flow."""
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ ERROR: GOOGLE_API_KEY environment variable not found.")
        return
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

    try:
        print("--- Starting New Stock Monitoring Request ---")
        asyncio.run(_run_stock_monitoring_async(user_query))
    except Exception as e:
        print(f"❌ An error occurred during the execution: {e}")
        raise

# --- Example Usage ---

if __name__ == "__main__":
    query_to_run = "Please monitor the stock price for XYZ."
    execute_stock_monitoring(query_to_run)