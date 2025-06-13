import streamlit as st
import os
from dotenv import load_dotenv
import traceback # Import traceback for detailed error printing
import asyncio

# --- Pydantic Import ---
from pydantic import BaseModel, Field

# --- Attempt to import ADK components ---
try:
    from google.adk.agents.sequential_agent import SequentialAgent
    from google.adk.agents.llm_agent import LlmAgent
    from google.adk.sessions import InMemorySessionService
    from google.adk.runners import Runner
    from google.adk.code_executors import BuiltInCodeExecutor
    ADK_AVAILABLE = True
except ImportError:
    st.error("Google ADK components not found. Please ensure 'google-adk' is installed.")
    ADK_AVAILABLE = False
    # Define dummy classes if ADK is not available to avoid NameError
    SequentialAgent = LlmAgent = InMemorySessionService = Runner = BuiltInCodeExecutor = object

# --- Attempt to import GenAI types ---
try:
    from google.genai import types as genai_types
    GENAI_TYPES_AVAILABLE = True
except ImportError:
    st.error("Google GenAI types not found. Please ensure 'google-generativeai' is installed.")
    GENAI_TYPES_AVAILABLE = False
    genai_types = None


st.set_page_config(page_title="AI Code Refinement Pipeline", layout="wide")
# --- Load Environment Variables ---
load_dotenv()

# --- Constants ---
APP_NAME = "streamlit_code_refinement_generator"
USER_ID = "streamlit_user_01"
SESSION_ID_PREFIX = "pipeline_session_"
GEMINI_MODEL = "gemini-1.5-flash"

# --- Pydantic Output Schemas for Agents ---
class CodeWriterOutput(BaseModel):
    """Pydantic model for the output of the CodeWriterAgent."""
    generated_code: str = Field(description="The Python code generated based on the user's request. Must be a valid Python code string.")

class CodeReviewerOutput(BaseModel):
    """Pydantic model for the output of the CodeReviewerAgent."""
    review_comments: str = Field(description="Constructive feedback and review comments for the provided code, formatted as bullet points in a single string.")

class CodeRefactorerOutput(BaseModel):
    """Pydantic model for the output of the CodeRefactorerAgent."""
    refactored_code: str = Field(description="The final, refactored Python code, based on the original code and review comments. Must be a valid Python code string.")

# --- Agent Definitions and Initialization ---
if ADK_AVAILABLE:
    if 'code_writer_agent' not in st.session_state:
        st.session_state.code_writer_agent = LlmAgent(
            name="CodeWriterAgent", model=GEMINI_MODEL,
            instruction="""You are a Code Writer AI.
Write Python code based on the user's request.
Respond ONLY with a JSON object that conforms to the required schema.
Format: {"generated_code": "print('hello world')"}""",
            description="Writes initial code.",
            output_schema=CodeWriterOutput,
            output_key="generated_code_obj"
        )
    if 'code_reviewer_agent' not in st.session_state:
        st.session_state.code_reviewer_agent = LlmAgent(
            name="CodeReviewerAgent", model=GEMINI_MODEL,
            instruction="""You are a Code Reviewer AI.
Review the Python code provided in the session state under the key 'generated_code_obj'.
Provide constructive feedback as bullet points (*). Focus on bugs, best practices, clarity, and error handling.
Respond ONLY with a JSON object containing the review comments.
Format: {"review_comments": "* comment 1\\n* comment 2"}""",
            description="Reviews code and provides feedback.",
            output_schema=CodeReviewerOutput,
            output_key="review_comments_obj"
        )
    if 'code_refactorer_agent' not in st.session_state:
        st.session_state.code_refactorer_agent = LlmAgent(
            name="CodeRefactorerAgent", model=GEMINI_MODEL,
            instruction="""You are a Code Refactorer AI.
Take the original Python code from 'generated_code_obj' and the review comments from 'review_comments_obj'.
Refactor the original code *strictly* based on the provided review comments.
If comments are empty or non-actionable, return the original code.
Respond ONLY with a JSON object containing the final refactored code.
Format: {"refactored_code": "print('hello, world') # Refactored based on comments"}""",
            description="Refactors code based on review comments.",
            output_schema=CodeRefactorerOutput,
            output_key="refactored_code_obj"
        )
    # --- MODIFIED: CodePipelineAgent now only has 3 sub-agents ---
    if 'code_pipeline_agent' not in st.session_state:
        st.session_state.code_pipeline_agent = SequentialAgent(
            name="CodeRefinementPipeline_Pydantic",
            sub_agents=[
                st.session_state.code_writer_agent,
                st.session_state.code_reviewer_agent,
                st.session_state.code_refactorer_agent,
            ]
        )
    if 'session_service' not in st.session_state:
        st.session_state.session_service = InMemorySessionService()
    if 'runner' not in st.session_state:
        st.session_state.runner = Runner(
            agent=st.session_state.code_pipeline_agent,
            app_name=APP_NAME,
            session_service=st.session_state.session_service
        )

# --- Helper Function (Keep as is) ---
def clean_code_output(text):
    if text is None: return ""
    text = text.strip()
    if text.startswith("```python"): text = text[len("```python"):].strip()
    elif text.startswith("```"): text = text[len("```"):].strip()
    if text.endswith("```"): text = text[:-len("```")].strip()
    return text

# --- Asynchronous function to run the ADK pipeline ---
async def run_debug_pipeline_async(user_query: str, current_session_id: str):
    session_service = st.session_state.session_service
    runner = st.session_state.runner

    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )

    initial_content = genai_types.Content(role='user', parts=[genai_types.Part(text=user_query)])
    event_list_for_debug = []
    final_response_text = "Pipeline did not produce a final text response."
    event_idx = 0

    async for event in runner.run_async(
        user_id=USER_ID, session_id=current_session_id, new_message=initial_content
    ):
        event_details = { "index": event_idx, "id": getattr(event, 'id', 'N/A'), "author": getattr(event, 'author', 'N/A'), "is_final": event.is_final_response(), "content_parts": [] }
        if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts') and event.content.parts:
            for part in event.content.parts:
                part_info = {}
                if hasattr(part, 'text') and part.text: part_info['text'] = part.text
                if part_info: event_details["content_parts"].append(part_info)
        event_list_for_debug.append(event_details)
        if event.is_final_response() and hasattr(event, 'content') and event.content.parts:
            if hasattr(event.content.parts[0], 'text'):
                final_response_text = event.content.parts[0].text
        event_idx += 1

    updated_session = await session_service.get_session(
        session_id=current_session_id, app_name=APP_NAME, user_id=USER_ID
    )
    session_state_from_adk = updated_session.state if updated_session and hasattr(updated_session, 'state') else {}

    def get_attribute_safely(obj, attr_name, key_name):
        """Helper to get data from either a Pydantic object or a dict."""
        if obj is None:
            return None
        if hasattr(obj, attr_name):
            return getattr(obj, attr_name)
        if isinstance(obj, dict):
            return obj.get(key_name)
        return None

    writer_obj = session_state_from_adk.get("generated_code_obj")
    reviewer_obj = session_state_from_adk.get("review_comments_obj")
    refactorer_obj = session_state_from_adk.get("refactored_code_obj")

    # --- MODIFIED: Return dictionary no longer includes execution_summary ---
    return {
        "generated_code": get_attribute_safely(writer_obj, "generated_code", "generated_code"),
        "review_comments": get_attribute_safely(reviewer_obj, "review_comments", "review_comments"),
        "refactored_code": get_attribute_safely(refactorer_obj, "refactored_code", "refactored_code"),
        "final_message": final_response_text,
        "event_list_for_debug": event_list_for_debug
    }

# --- Streamlit UI ---
st.title("🚧 AI Code Refinement Pipeline 🚧")
# --- MODIFIED: UI description updated for the 3-step process ---
st.markdown("Enter a description -> **Write Code** -> **Review Code** -> **Refactor Code**")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Your Request")
    user_query = st.text_area("Describe the Python code you want:", height=100, placeholder="e.g., a function to calculate the factorial of a number")

    if 'session_counter' not in st.session_state:
        st.session_state.session_counter = 0

    if st.button("⚙️ Run Code Refinement Pipeline", disabled=not ADK_AVAILABLE):
        if user_query and ADK_AVAILABLE and GENAI_TYPES_AVAILABLE:
            st.session_state.session_counter += 1
            current_session_id = f"{SESSION_ID_PREFIX}{st.session_state.session_counter}"

            st.session_state.results = {}
            st.session_state.error = None
            st.session_state.ran_query = user_query

            status_placeholder = st.empty()
            try:
                with st.spinner("🤖 Running AI pipeline with Pydantic validation..."):
                    status_placeholder.info("Pipeline initiated...")
                    results_data = asyncio.run(run_debug_pipeline_async(user_query, current_session_id))
                    st.session_state.results = results_data

                    if results_data and (results_data.get("generated_code") or results_data.get("refactored_code")):
                        status_placeholder.success("✅ Pipeline finished successfully!")
                    else:
                        status_placeholder.warning("⚠️ Pipeline finished, but some results might be missing.")

            except Exception as e:
                st.error(f"An error occurred during pipeline execution: {e}")
                st.code(traceback.format_exc())
                st.session_state.error = str(e)
                st.session_state.results = {}
                status_placeholder.error("❌ Pipeline failed.")

        elif not user_query:
            st.warning("Please enter a description for the code.")
        elif not ADK_AVAILABLE or not GENAI_TYPES_AVAILABLE:
            st.error("Cannot run pipeline: Required ADK/GenAI libraries missing.")

    if 'ran_query' in st.session_state and st.session_state.ran_query:
         st.markdown("**Last Run Request:**"); st.info(st.session_state.ran_query)

with col2:
    st.subheader("2. Agent Pipeline Results")

    if 'results' in st.session_state and st.session_state.results:
        results = st.session_state.results

        with st.expander("🖋️ Step 1: Initial Code Generation (CodeWriterAgent)", expanded=True):
            generated_code = clean_code_output(results.get("generated_code"))
            if generated_code: st.code(generated_code, language="python")
            else: st.warning("No code generated or retrieved.")

        with st.expander("🔍 Step 2: Code Review (CodeReviewerAgent)", expanded=True):
            review_comments = results.get("review_comments")
            if review_comments: st.markdown(review_comments)
            else: st.warning("No review comments generated or retrieved.")

        with st.expander("🔧 Step 3: Refactored Code (CodeRefactorerAgent)", expanded=True):
            refactored_code_raw = results.get("refactored_code")
            refactored_code_cleaned = clean_code_output(refactored_code_raw)
            if refactored_code_cleaned: st.code(refactored_code_cleaned, language="python")
            else: st.warning("No refactored code generated or retrieved.")

        # --- MODIFIED: Code execution expander has been removed ---

        st.divider()
        st.subheader("💬 Final Message from Pipeline")
        final_message = results.get("final_message")
        if final_message: st.info(final_message)
        else: st.warning("No final message captured from the pipeline.")

        event_list = results.get("event_list_for_debug")
        if event_list:
            with st.expander("📋 View Detailed Event Log", expanded=False):
                st.json(event_list)

        st.markdown("---")
        st.caption("Powered by Google ADK and Streamlit")

    elif 'error' in st.session_state and st.session_state.error:
        st.error(f"Pipeline execution failed: {st.session_state.error}")
    else:
        st.info("Enter a request on the left to see the results here.")