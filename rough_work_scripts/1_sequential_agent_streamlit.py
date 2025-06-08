import streamlit as st
import asyncio
import uuid # For unique session IDs

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.genai.types import Content, Part

from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables (e.g., API keys)
load_dotenv()

# --- Constants ---
APP_NAME = "code_pipeline_app"
USER_ID = "dev_user_01"
# Using a known valid model. Change if "gemini-2.0-flash" is specifically needed and available.
GEMINI_MODEL = "gemini-1.5-flash-latest"

# Streamlit session state keys
ST_RESULTS_KEY = 'pipeline_results'
ST_ERROR_KEY = 'pipeline_error'
ST_QUERY_KEY = 'user_query_input'

# --- Pydantic Models for Agent Outputs ---
class CodeWriterOutput(BaseModel):
    code: str
    code_explanation: str

class CodeReviewerOutput(BaseModel):
    code: str # The code that was reviewed
    code_review: str

# --- 1. Define Sub-Agents for Each Pipeline Stage ---

# Code Writer Agent
code_writer_agent = LlmAgent(
    name="CodeWriterAgent",
    model=GEMINI_MODEL,
    instruction="""You are a Code Writer AI.
    Based on the user's request, write the initial Python code and provide a brief explanation.
    Output your response as a JSON object with two keys: 'code' (the Python code block) and 'code_explanation' (a brief explanation of the code).
    """,
    description="Writes initial code based on a specification.",
    output_key="generated_code_data", # Stores CodeWriterOutput instance
    output_schema=CodeWriterOutput
)

# Code Reviewer Agent
code_reviewer_agent = LlmAgent(
    name="CodeReviewerAgent",
    model=GEMINI_MODEL,
    instruction="""You are a Code Reviewer AI.
    You will be provided with Python code. Review it and provide constructive feedback.
    Output your response as a JSON object with two keys: 'code' (the exact Python code you reviewed) and 'code_review' (your feedback).
    Focus on clarity, correctness, potential errors, style issues, or improvements.
    """,
    description="Reviews code and provides feedback.",
    output_key="review_data", # Stores CodeReviewerOutput instance
    output_schema=CodeReviewerOutput
)

# Code Refactorer Agent
code_refactorer_agent = LlmAgent(
    name="CodeRefactorerAgent",
    model=GEMINI_MODEL,
    instruction="""You are a Code Refactorer AI.
    You will be provided with original Python code and review comments.
    Refactor the original code to address the feedback and improve its quality.
    Output your response as a JSON object with two keys: 'code' (the final, refactored Python code block) and 'code_explanation' (a brief explanation of the changes made).
    """,
    description="Refactors code based on review comments.",
    output_key="refactored_code_data", # Stores CodeWriterOutput instance
    output_schema=CodeWriterOutput # Expects refactored code and explanation
)

# --- 2. Create the SequentialAgent ---
code_pipeline_agent = SequentialAgent(
    name="CodePipelineAgent",
    sub_agents=[code_writer_agent, code_reviewer_agent, code_refactorer_agent]
)

# --- 3. Session Service ---
session_service = InMemorySessionService()

# --- 4. Streamlit UI and Agent Interaction Logic ---

async def run_code_pipeline(query: str):
    """
    Runs the code generation and refinement pipeline.
    """
    current_session_id = str(uuid.uuid4()) # Unique session ID for each run

    _ = await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )
    
    runner = Runner(
        agent=code_pipeline_agent,
        app_name=APP_NAME,
        session_service=session_service
    )
    
    initial_message = Content(role='user', parts=[Part(text=query)])

    # Stream events from the runner.
    # For this UI, we're mainly interested in the final state after all agents run.
    async for _event in runner.run_async(user_id=USER_ID, session_id=current_session_id, new_message=initial_message):
        # Can inspect _event here for granular progress if ADK supports it well for sub-agents
        pass

    session_state_data = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )
    
    initial_code_output: CodeWriterOutput = session_state_data.state.get("generated_code_data")
    review_output: CodeReviewerOutput = session_state_data.state.get("review_data")
    refactored_code_output: CodeWriterOutput = session_state_data.state.get("refactored_code_data")

    print('1.',initial_code_output)
    print('2.',review_output)
    print('3.',refactored_code_output)

    return {
        "initial_code": initial_code_output['code'] if initial_code_output else "Error: Initial code not generated.",
        "initial_code_explanation": initial_code_output['code_explanation'] if initial_code_output else "No explanation provided.",
        "reviewed_code_input": review_output['code'] if review_output else "Error: Code for review not captured.",
        "review_comments": review_output['code_review'] if review_output else "Error: Review not generated.",
        "refactored_code": refactored_code_output['code'] if refactored_code_output else "Error: Code not refactored.",
        "refactored_code_explanation": refactored_code_output['code_explanation'] if refactored_code_output else "No explanation provided."
    }

def streamlit_app():
    st.set_page_config(layout="wide", page_title="Code Pipeline AI")
    st.title("📝 AI Code Generation & Refinement Pipeline")
    st.markdown("""
        Enter a description of the Python code you need.
        The AI pipeline will:
        1.  **Write** the initial code.
        2.  **Review** the generated code.
        3.  **Refactor** the code based on the review.
    """)

    if ST_RESULTS_KEY not in st.session_state:
        st.session_state[ST_RESULTS_KEY] = None
    if ST_ERROR_KEY not in st.session_state:
        st.session_state[ST_ERROR_KEY] = None

    with st.sidebar:
        st.header("Controls")
        user_query = st.text_area(
            "Enter your code specification:",
            height=150,
            key=ST_QUERY_KEY,
            placeholder="e.g., a Python function that calculates the factorial of a number"
        )

        if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
            if user_query:
                st.session_state[ST_RESULTS_KEY] = None
                st.session_state[ST_ERROR_KEY] = None
                
                status_text = st.empty()
                with st.spinner("🧠 Running AI agents... This may take a moment."):
                    status_text.info("Pipeline initiated...")
                    try:
                        results = asyncio.run(run_code_pipeline(user_query))
                        st.session_state[ST_RESULTS_KEY] = results
                        status_text.success("✅ Pipeline completed!")
                    except Exception as e:
                        st.session_state[ST_ERROR_KEY] = f"An error occurred: {str(e)}"
                        st.error(st.session_state[ST_ERROR_KEY]) # Display error in sidebar
                        status_text.error("❌ Pipeline failed.")
            else:
                st.warning("Please enter a code specification.")
        
        st.markdown("---")
        st.caption(f"Using Model: `{GEMINI_MODEL}`")
        st.caption(f"ADK App Name: `{APP_NAME}`")

    # Main area for displaying results
    if st.session_state[ST_ERROR_KEY] and not st.session_state[ST_RESULTS_KEY]:
        st.error(f"Pipeline Error: {st.session_state[ST_ERROR_KEY]}") # Display error in main area if it happened

    if st.session_state[ST_RESULTS_KEY]:
        results = st.session_state[ST_RESULTS_KEY]
        
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("1. Initial Code (Writer)")
            st.markdown("**Generated Code:**")
            st.code(results["initial_code"], language="python")
            st.markdown("**Explanation:**")
            st.info(results["initial_code_explanation"])

        with col2:
            st.subheader("2. Code Review (Reviewer)")
            st.markdown("**Review Comments:**")
            st.warning(results["review_comments"]) # Using warning for visibility
            with st.expander("See code submitted for review"):
                 st.code(results["reviewed_code_input"], language="python")


        with col3:
            st.subheader("3. Refactored Code (Refactorer)")
            st.markdown("**Refactored Code:**")
            st.code(results["refactored_code"], language="python")
            st.markdown("**Refactoring Explanation:**")
            st.success(results["refactored_code_explanation"]) # Using success for visibility
    else:
        if not st.session_state[ST_ERROR_KEY]: # Initial state, no run yet
             st.info("Enter a code specification in the sidebar and click 'Run Pipeline' to see the results.")

if __name__ == "__main__":
    streamlit_app()