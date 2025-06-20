import asyncio
import uuid
import os
from typing import Dict, Any

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.genai.types import Content, Part
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv
from pydantic import BaseModel

# --- Constants ---
APP_NAME = "code_pipeline_module_app"
USER_ID = "dev_user_01"
# Make sure to use a valid model available to you.
GEMINI_MODEL = "gemini-2.0-flash-001"

# --- Pydantic Models for Agent Outputs ---
class CodeWriterOutput(BaseModel):
    code: str
    code_explanation: str

class CodeReviewerOutput(BaseModel):
    code: str  # The code that was reviewed
    code_review: str

# --- Agent and Session Service Setup (Instantiated once on import) ---

# Code Writer Agent
_code_writer_agent = LlmAgent(
    name="CodeWriterAgent",
    model=GEMINI_MODEL,
    instruction="""You are a Code Writer AI.
    Based on the user's request, write the initial Python code and provide a brief explanation.
    Output your response as a JSON object with two keys: 'code' (the Python code block) and 'code_explanation' (a brief explanation of the code).
    """,
    output_key="generated_code_data",
    output_schema=CodeWriterOutput,
)

# Code Reviewer Agent
_code_reviewer_agent = LlmAgent(
    name="CodeReviewerAgent",
    model=GEMINI_MODEL,
    instruction="""You are a Code Reviewer AI.
    You will be provided with Python code. Review it and provide constructive feedback.
    Output your response as a JSON object with two keys: 'code' (the exact Python code you reviewed) and 'code_review' (your feedback).
    Focus on clarity, correctness, potential errors, style issues, or improvements.
    """,
    output_key="review_data",
    output_schema=CodeReviewerOutput,
)

# Code Refactorer Agent
_code_refactorer_agent = LlmAgent(
    name="CodeRefactorerAgent",
    model=GEMINI_MODEL,
    instruction="""You are a Code Refactorer AI.
    You will be provided with original Python code and review comments.
    Refactor the original code to address the feedback and improve its quality.
    Output your response as a JSON object with two keys: 'code' (the final, refactored Python code block) and 'code_explanation' (a brief explanation of the changes made).
    """,
    output_key="refactored_code_data",
    output_schema=CodeWriterOutput,
)

# The Sequential Agent Pipeline
_code_pipeline_agent = SequentialAgent(
    name="CodePipelineAgent",
    sub_agents=[_code_writer_agent, _code_reviewer_agent, _code_refactorer_agent],
)

# Session Service
_session_service = InMemorySessionService()


# ==============================================================================
# CORRECTED FUNCTION
# ==============================================================================
async def execute_code_pipeline(user_query: str) -> Dict[str, Any]:
    """
    Executes the complete Code Generation, Review, and Refactoring pipeline asynchronously.

    This function leverages an AI-powered pipeline to generate code based on a user's query,
    review the generated code, and refactor it for improvements. It ensures that the process
    is managed within a session and returns comprehensive results from each stage of the pipeline.

    Args:
        user_query (str): A string describing the desired functionality of the code.
                          Example: "a function to calculate the nth Fibonacci number".

    Returns:
        dict: A dictionary containing the results from each stage of the pipeline:
            - 'initial_code' (str): The code generated initially.
            - 'initial_code_explanation' (str): Explanation of the initially generated code.
            - 'reviewed_code_input' (str): The code that was reviewed.
            - 'review_comments' (str): Comments and feedback from the code review.
            - 'refactored_code' (str): The refactored version of the code.
            - 'refactored_code_explanation' (str): Explanation of the refactored code.
            - 'error' (str, optional): An error message if the pipeline fails at any stage.
    """
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        return {"error": "GOOGLE_API_KEY environment variable not found."}

    try:
        print(f"▶️  Running AI pipeline for query: '{user_query[:50]}...'")
        current_session_id = str(uuid.uuid4())

        # Directly use 'await' since we are in an async function
        await _session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        runner = Runner(
            agent=_code_pipeline_agent,
            app_name=APP_NAME,
            session_service=_session_service,
        )

        initial_message = Content(role="user", parts=[Part(text=user_query)])

        async for _ in runner.run_async(
            user_id=USER_ID, session_id=current_session_id, new_message=initial_message
        ):
            pass  # We just need to let the runner complete

        session_state_data = await _session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        # The ADK now correctly parses Pydantic models into dicts in the state
        initial_code_output = session_state_data.state.get("generated_code_data")
        review_output = session_state_data.state.get("review_data")
        refactored_code_output = session_state_data.state.get("refactored_code_data")

        print("✅ Pipeline completed successfully.")
        return {
            "initial_code": initial_code_output.get("code") if initial_code_output else "Error: Initial code not generated.",
            "initial_code_explanation": initial_code_output.get("code_explanation") if initial_code_output else "No explanation provided.",
            "reviewed_code_input": review_output.get("code") if review_output else "Error: Code for review not captured.",
            "review_comments": review_output.get("code_review") if review_output else "Error: Review not generated.",
            "refactored_code": refactored_code_output.get("code") if refactored_code_output else "Error: Code not refactored.",
            "refactored_code_explanation": refactored_code_output.get("code_explanation") if refactored_code_output else "No explanation provided.",
        }

    except Exception as e:
        print(f"❌ Pipeline failed with an error: {e}")
        # Print the full traceback for better debugging
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "initial_code": "Pipeline failed.",
            "initial_code_explanation": "Pipeline failed.",
            "reviewed_code_input": "Pipeline failed.",
            "review_comments": "Pipeline failed.",
            "refactored_code": "Pipeline failed.",
            "refactored_code_explanation": "Pipeline failed.",
        }
    

def add(a: int, b: int) -> dict:
    """Adds two numbers together.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        dict: The result of the addition.
    """
    return {
        "status": "success",
        "result": a + b
    }

def subtract(a: int, b: int) -> dict:
    """Subtracts the second number from the first number.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        dict: The result of the subtraction.
    """
    return {
        "status": "success",
        "result": a - b
    }

def multiply(a: int, b: int) -> dict:
    """Multiplies two numbers together.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        dict: The result of the multiplication.
    """
    return {
        "status": "success",
        "result": a * b
    }


import datetime
from zoneinfo import ZoneInfo
def get_weather(city: str) -> dict:
    """Retrieves the current weather report for a specified city.

    Args:
        city (str): The name of the city for which to retrieve the weather report.

    Returns:
        dict: status and result or error msg.
    """
    if city.lower() == "new york":
        return {
            "status": "success",
            "report": (
                "The weather in New York is sunny with a temperature of 25 degrees"
                " Celsius (77 degrees Fahrenheit)."
            ),
        }
    else:
        return {
            "status": "error",
            "error_message": f"Weather information for '{city}' is not available.",
        }


def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city.

    Args:
        city (str): The name of the city for which to retrieve the current time.

    Returns:
        dict: status and result or error msg.
    """

    if city.lower() == "new york":
        tz_identifier = "America/New_York"
    else:
        return {
            "status": "error",
            "error_message": (
                f"Sorry, I don't have timezone information for {city}."
            ),
        }

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    report = (
        f'The current time in {city} is {now.strftime("%Y-%m-%d %H:%M:%S %Z%z")}'
    )
    return {"status": "success", "report": report}

from typing import AsyncGenerator
async def monitor_stock_price(stock_symbol: str) -> AsyncGenerator[str, None]:
  """This function will monitor the price for the given stock_symbol in a continuous, streaming and asynchronously way."""
  print(f"Start monitor stock price for {stock_symbol}!")

  # Let's mock stock price change.
  await asyncio.sleep(4)
  price_alert1 = f"the price for {stock_symbol} is 300"
  yield price_alert1
  print(price_alert1)

  await asyncio.sleep(4)
  price_alert1 = f"the price for {stock_symbol} is 400"
  yield price_alert1
  print(price_alert1)

  await asyncio.sleep(20)
  price_alert1 = f"the price for {stock_symbol} is 900"
  yield price_alert1
  print(price_alert1)

  await asyncio.sleep(20)
  price_alert1 = f"the price for {stock_symbol} is 500"
  yield price_alert1
  print(price_alert1)

supervisor = LlmAgent(
    name="Supervisor",
    model="gemini-2.0-flash-live-001", # Use a consistent and available model
    instruction="""
    You are a smart agent responsible for directing user requests to the appropriate sub-agents. Your main role is to evaluate the user's query and assign it to the correct sub-agent.

    Upon receiving a user query, you must analyze its content to determine which sub-agent tool should handle it. You have the following tools available for different types of operations:

    Add tool
    Subtract tool
    Multiply tool
    Get current time tool
    Get weather tool
    Execute code pipeline tool
    monitor_stock_price tool
Your task is to assess the user’s query and decide which tool is best suited for processing it.
    """,
    description="Intelligent router for directing user queries to the appropriate sub-agent tools.",
    tools=[add,subtract,multiply,get_current_time,get_weather,execute_code_pipeline,monitor_stock_price],  # This part is correct
)