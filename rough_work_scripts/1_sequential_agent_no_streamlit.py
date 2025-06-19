# code_pipeline_module.py

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


async def _run_async_pipeline(query: str) -> Dict[str, Any]:
    """Internal async function to run the agent pipeline."""
    current_session_id = str(uuid.uuid4())

    await _session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )

    runner = Runner(
        agent=_code_pipeline_agent,
        app_name=APP_NAME,
        session_service=_session_service,
    )

    initial_message = Content(role="user", parts=[Part(text=query)])

    async for _ in runner.run_async(
        user_id=USER_ID, session_id=current_session_id, new_message=initial_message
    ):
        pass

    session_state_data = await _session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )

    initial_code_output: CodeWriterOutput = session_state_data.state.get("generated_code_data")
    review_output: CodeReviewerOutput = session_state_data.state.get("review_data")
    refactored_code_output: CodeWriterOutput = session_state_data.state.get("refactored_code_data")

    # print(":>>>>>",initial_code_output, type(initial_code_output))
    # print(":>>>>>",review_output, type(review_output))

    return {
        "initial_code": initial_code_output.get("code") if initial_code_output else "Error: Initial code not generated.",
        "initial_code_explanation": initial_code_output.get("code_explanation") if initial_code_output else "No explanation provided.",
        "reviewed_code_input": review_output.get("code") if review_output else "Error: Code for review not captured.",
        "review_comments": review_output.get("code_review") if review_output else "Error: Review not generated.",
        "refactored_code": refactored_code_output.get("code") if refactored_code_output else "Error: Code not refactored.",
        "refactored_code_explanation": refactored_code_output.get("code_explanation") if refactored_code_output else "No explanation provided.",
    }

def execute_code_pipeline(user_query: str) -> Dict[str, Any]:
    """
    Executes the full Code Generation, Review, and Refactoring pipeline.

    This is a synchronous wrapper that handles the async execution of the ADK agents.

    Args:
        user_query: A string describing the desired functionality of the code.
                    e.g., "a function to calculate the nth fibonacci number".

    Returns:
        A dictionary containing the results from each stage of the pipeline.
        Includes an 'error' key if the pipeline fails.
    """
    # Load environment variables (e.g., API keys) from a .env file
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        return {"error": "GOOGLE_API_KEY environment variable not found."}
        
    try:
        print(f"▶️  Running AI pipeline for query: '{user_query[:50]}...'")
        # Run the internal async function from this synchronous one
        result = asyncio.run(_run_async_pipeline(user_query))
        print("✅ Pipeline completed successfully.")
        return result
    except Exception as e:
        print(f"❌ Pipeline failed with an error: {e}")
        return {
            "error": str(e),
            "initial_code": "Pipeline failed.",
            "initial_code_explanation": "Pipeline failed.",
            "reviewed_code_input": "Pipeline failed.",
            "review_comments": "Pipeline failed.",
            "refactored_code": "Pipeline failed.",
            "refactored_code_explanation": "Pipeline failed.",
        }

# This block allows you to test the module directly if needed
if __name__ == "__main__":
    import json
    
    print("--- Running module in test mode ---")
    test_query = "a python class for a simple bank account with deposit and withdraw methods"
    
    # Call the main function
    pipeline_result = execute_code_pipeline(test_query)

    # Pretty-print the JSON result
    print("\n--- Pipeline Result ---")
    print(json.dumps(pipeline_result, indent=2))
    print("-----------------------")