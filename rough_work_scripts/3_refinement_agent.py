import streamlit as st
import os
from dotenv import load_dotenv
import traceback # Import traceback for detailed error printing
import asyncio # <<< ADDED IMPORT

# --- Attempt to import ADK components ---

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.code_executors import BuiltInCodeExecutor # Assuming this path is correct for your ADK version

ADK_AVAILABLE = True

# --- Attempt to import GenAI types ---

from google.genai import types as genai_types
GENAI_TYPES_AVAILABLE = True

st.set_page_config(page_title="AI Code Pipeline (Debug)", layout="wide")
# --- Load Environment Variables ---
load_dotenv()

# --- Constants ---
APP_NAME = "streamlit_code_pipeline_generator"
USER_ID = "streamlit_user_01"
SESSION_ID_PREFIX = "pipeline_session_"
GEMINI_MODEL = "gemini-2.0-flash" # Using the model from your debug code

# --- Agent Definitions and Initialization (DEBUGGING VERSION) ---
if ADK_AVAILABLE:
    if 'code_writer_agent' not in st.session_state:
        st.session_state.code_writer_agent = LlmAgent(
            name="CodeWriterAgent", model=GEMINI_MODEL,
            instruction="Write Python code based on user request. Output only raw code in ```python ... ```.",
            description="Writes initial code.", output_key="generated_code"
        )
    if 'code_reviewer_agent' not in st.session_state:
        st.session_state.code_reviewer_agent = LlmAgent(
            name="CodeReviewerAgent", model=GEMINI_MODEL,
            instruction="""You are a Code Reviewer AI.
    Review the Python code provided in the session state under the key 'generated_code'.
    Provide constructive feedback as bullet points (*). Focus on:
    * Potential bugs or errors.
    * Adherence to Python best practices (PEP 8).
    * Possible improvements for clarity, efficiency, or robustness.
    * Missing error handling or edge cases.
    Output only the review comments. Do not include the code itself in your output.
    """,
            description="Reviews code and provides feedback.", output_key="review_comments"
        )
    if 'code_refactorer_agent' not in st.session_state:
        st.session_state.code_refactorer_agent = LlmAgent(
            name="CodeRefactorerAgent", model=GEMINI_MODEL,
            instruction="""You are a Code Refactorer AI.
    Take the original Python code provided in the session state key 'generated_code'
    and the review comments found in the session state key 'review_comments'.
    Refactor the original code *strictly* based on the provided review comments to improve its quality, clarity, and correctness.
    If the review comments are empty or non-actionable, return the original code.
    Output *only* the final, refactored Python code block, enclosed in triple backticks (```python ... ```).
    """,
            description="Refactors code based on review comments.", output_key="refactored_code"
        )
    if 'code_interpreter_agent' not in st.session_state:
        st.session_state.code_interpreter_agent = LlmAgent(
            name="CodeInterpreterAgent", model=GEMINI_MODEL,
            tools=[BuiltInCodeExecutor] if BuiltInCodeExecutor else [], # Check if tool is available
            instruction="""You are a Code Execution Assistant.
    1. Examine the session state for Python code, prioritizing the key 'refactored_code'. If it's empty or absent, use the code from 'generated_code'.
    2. Extract *only* the raw Python code from the relevant state key (remove markdown fences like ```python).
    3. If code is found, execute it using the provided code execution tool.
    - For code defining functions/classes without direct execution, add simple example usage if feasible (e.g., call a function with sample inputs) to test its execution. Run scripts directly.
    4. Your final output *must* be only a plain text summary detailing the execution outcome. Format:
    Execution Outcome: [Success/Failure]
    Output:
    [Captured stdout/stderr or 'No output captured.']""",
            description="Executes the generated/refactored code and reports the outcome.",
            output_key="execution_summary"
        )
    if 'code_pipeline_agent' not in st.session_state:
        st.session_state.code_pipeline_agent = SequentialAgent(
            name="CodePipelineAgent_Debug",
            sub_agents=[
                st.session_state.code_writer_agent,
                st.session_state.code_reviewer_agent,
                st.session_state.code_refactorer_agent,
                # st.session_state.code_interpreter_agent
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

# --- New Asynchronous function to run the ADK pipeline ---
async def run_debug_pipeline_async(user_query: str, current_session_id: str):
    session_service = st.session_state.session_service
    runner = st.session_state.runner

    # Create a new ADK session for this specific run
    await session_service.create_session( # <<< ADDED await
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )

    initial_content = genai_types.Content(role='user', parts=[genai_types.Part(text=user_query)])

    event_list_for_debug = []
    final_response_text = "Pipeline did not produce a final text response." # Default
    event_idx = 0

    # Stream events from the runner.
    async for event in runner.run_async( # <<< CHANGED to run_async and async for
        user_id=USER_ID, session_id=current_session_id, new_message=initial_content
    ):
        event_details = {
            "index": event_idx,
            "id": getattr(event, 'id', 'N/A'),
            "author": getattr(event, 'author', 'N/A'),
            "is_final": event.is_final_response(),
            "interrupted": getattr(event, 'interrupted', None),
            "error_code": getattr(event, 'error_code', None),
            "error_message": getattr(event, 'error_message', None),
            "content_parts": []
        }
        if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts') and event.content.parts:
            for part in event.content.parts:
                part_info = {}
                if hasattr(part, 'text') and part.text: part_info['text'] = part.text
                if hasattr(part, 'executable_code'): part_info['executable_code'] = str(part.executable_code)
                if hasattr(part, 'code_execution_result'): part_info['code_execution_result'] = str(part.code_execution_result)
                if part_info:
                    event_details["content_parts"].append(part_info)
        
        event_list_for_debug.append(event_details)

        if event.is_final_response(): # This is the final event from the SequentialAgent
            if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts') and event.content.parts:
                first_part = event.content.parts[0]
                if hasattr(first_part, 'text') and first_part.text:
                    final_response_text = first_part.text
        event_idx += 1

    # Retrieve the final state
    updated_session = await session_service.get_session( # <<< ADDED await
        session_id=current_session_id, app_name=APP_NAME, user_id=USER_ID
    )
    session_state_from_adk = updated_session.state if updated_session and hasattr(updated_session, 'state') else {}

    return {
        "generated_code": session_state_from_adk.get("generated_code"),
        "review_comments": session_state_from_adk.get("review_comments"),
        "refactored_code": session_state_from_adk.get("refactored_code"),
        "execution_summary": session_state_from_adk.get("execution_summary"),
        "final_message": final_response_text,
        "event_list_for_debug": event_list_for_debug # Return events for later display
    }

# --- Streamlit UI ---
st.title("🚧 AI Code Generation Pipeline 🚧")
st.markdown("Enter a description -> Write Code -> Review Code -> Refactor Code -> Execute Code (Code Interpreter)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Your Request")
    user_query = st.text_area("Describe the Python code you want:", height=100, placeholder="e.g., print hello sam in python")

    if 'session_counter' not in st.session_state: # Initialize session_counter if not present
        st.session_state.session_counter = 0

    if st.button("⚙️ Run Code Generator Pipeline", disabled=not ADK_AVAILABLE):
        if user_query and ADK_AVAILABLE and GENAI_TYPES_AVAILABLE:
            st.session_state.session_counter += 1 # Increment for unique session ID
            current_session_id = f"{SESSION_ID_PREFIX}{st.session_state.session_counter}"
            
            st.session_state.results = {} # Clear previous results
            st.session_state.error = None
            st.session_state.ran_query = user_query # Store query

            status_placeholder = st.empty() # For status messages
            try:
                with st.spinner("🤖 Running AI pipeline... This may take a moment."):
                    status_placeholder.info("Pipeline initiated...")
                    # Run the asynchronous pipeline function
                    results_data = asyncio.run(run_debug_pipeline_async(user_query, current_session_id))
                    st.session_state.results = results_data
                    
                    if results_data and results_data.get("generated_code"): # Check if results are meaningful
                        status_placeholder.success("✅ Pipeline finished successfully!")
                    else:
                        status_placeholder.warning("⚠️ Pipeline finished, but some results might be missing.")
                
            except Exception as e:
                st.error(f"An error occurred during pipeline execution: {e}")
                st.code(traceback.format_exc())
                st.session_state.error = str(e)
                st.session_state.results = {} # Clear results on error
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
            st.markdown(f"**Review Comments:**\n```\n{review_comments}\n```" if review_comments else "No review comments generated or retrieved.")

        with st.expander("🔧 Step 3: Refactored Code (CodeRefactorerAgent)", expanded=True):
            refactored_code_raw = results.get("refactored_code")
            refactored_code_cleaned = clean_code_output(refactored_code_raw)
            if refactored_code_cleaned: st.code(refactored_code_cleaned, language="python")
            else: st.warning("No refactored code generated or retrieved.")
            if refactored_code_raw and not refactored_code_cleaned:
                 st.caption(f"Raw refactor output (if any): {refactored_code_raw}")


        with st.expander("🚀 Step 4: Code Execution (CodeInterpreterAgent)", expanded=True):
            execution_summary = results.get("execution_summary")
            st.markdown(f"**Execution Summary:**\n```\n{execution_summary}\n```" if execution_summary else "No execution summary generated or retrieved.")

        st.divider()
        st.subheader("💬 Final Message from Pipeline")
        final_message = results.get("final_message")
        if final_message: st.info(final_message)
        else: st.warning("No final message captured from the pipeline.")
        
        # Displaying detailed event log
        event_list = results.get("event_list_for_debug")
        if event_list:
            with st.expander("📋 View Detailed Event Log", expanded=False):
                st.json(event_list)
        
        st.markdown("---")
        st.caption("Powered by Google ADK and Streamlit")

    elif 'error' in st.session_state and st.session_state.error:
        st.error(f"Pipeline execution failed: {st.session_state.error}")
    elif not ADK_AVAILABLE:
         st.info("Enter a request and click 'Run Code Generator Pipeline' once ADK libraries are available.")
    else:
        st.info("Enter a request on the left to see the results here.")