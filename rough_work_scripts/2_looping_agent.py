import streamlit as st
import asyncio
import uuid # For unique session IDs

from google.adk.agents.loop_agent import LoopAgent
from google.adk.agents.llm_agent import LlmAgent
from google.genai import types as genai_types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv

# Load environment variables (e.g., API keys)
load_dotenv()

# --- Constants ---
APP_NAME = "iterative_doc_writer_app"
USER_ID = "dev_user_01"
GEMINI_MODEL = "gemini-1.5-flash-latest"

# --- State Keys ---
STATE_CURRENT_DOC = "current_document"
STATE_CRITICISM = "criticism"
# The key 'initial_topic' is used in the WriterAgent's prompt
# and its value is expected to be derived from the initial user message.

# Streamlit session state keys
ST_LOOP_RESULTS_KEY = 'loop_results'
ST_ERROR_KEY = 'loop_error'
ST_TOPIC_KEY = 'user_topic_input'

# --- Agent Definitions ---
writer_agent = LlmAgent(
    name="WriterAgent",
    model=GEMINI_MODEL,
    instruction=f"""
    You are a Creative Writer AI.
    Your goal is to produce a short document.
    Check the ADK session state for a key named '{STATE_CURRENT_DOC}' and also consider the initial user message which provides the topic.
    If '{STATE_CURRENT_DOC}' is empty or does not exist in the ADK session state, write a very short (1-2 sentence) story or document based on the initial topic provided by the user.
    If '{STATE_CURRENT_DOC}' *already exists* in the ADK session state and there is content in a state key named '{STATE_CRITICISM}', refine '{STATE_CURRENT_DOC}' according to the comments in '{STATE_CRITICISM}'.
    Output *only* the new story/document.
    """,
    description="Writes or refines the document draft.",
    output_key=STATE_CURRENT_DOC # Saves output to ADK session state
)

critic_agent = LlmAgent(
    name="CriticAgent",
    model=GEMINI_MODEL,
    instruction=f"""
    You are a Constructive Critic AI.
    Review the document provided in the ADK session state key '{STATE_CURRENT_DOC}'.
    Provide 1-2 brief, actionable suggestions for improvement (e.g., "Make it more exciting", "Add more detail about X").
    Output *only* the critique.
    """,
    description="Reviews the current document draft.",
    output_key=STATE_CRITICISM # Saves critique to ADK session state
)

# Create the LoopAgent
loop_agent = LoopAgent(
    name="DocumentIterationLoopAgent",
    sub_agents=[writer_agent, critic_agent],
    max_iterations=3
)

# --- Session Service ---
session_service = InMemorySessionService()

# --- ADK Interaction Logic for Streamlit ---

async def run_loop_iterations_async(initial_topic: str):
    """
    Runs the document writing and critiquing loop.
    The initial_topic is passed as the first message to the LoopAgent.
    Returns the final document and final criticism from the ADK session state.
    """
    current_session_id = str(uuid.uuid4()) # Unique session ID for each run

    # 1. Create the session.
    _ = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=current_session_id
    )

    runner = Runner(
        agent=loop_agent,
        app_name=APP_NAME,
        session_service=session_service
    )

    # The initial_topic from the user is passed as the first message.
    # The WriterAgent's prompt is designed to use this when current_document is not yet in state.
    start_message = genai_types.Content(role='user', parts=[genai_types.Part(text=initial_topic)])

    async for _event in runner.run_async(user_id=USER_ID, session_id=current_session_id, new_message=start_message):
        # Loop to ensure the agent processing completes.
        pass

    # After the loop completes, get the full session data
    session_snapshot = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
    )

    # Extract the final document and criticism from the ADK session state
    final_doc = session_snapshot.state.get(STATE_CURRENT_DOC, "Error: Final document not found in state.")
    final_criticism = session_snapshot.state.get(STATE_CRITICISM, "Note: No final criticism was recorded in state.") # More neutral message

    # For debugging in the console
    print("\n--- ADK Session State after Loop ---")
    print(f"Final state of the snapshot: {session_snapshot.state}")
    print(f"Retrieved Document: {final_doc}")
    print(f"Retrieved Criticism: {final_criticism}")
    print("-----------------------------------\n")

    return {
        "final_document": final_doc,
        "final_criticism": final_criticism,
        "max_iterations_configured": loop_agent.max_iterations # For display in sidebar
    }

# --- Streamlit UI ---
def streamlit_loop_app():
    st.set_page_config(layout="wide", page_title="Iterative Document Writer AI")
    st.title("📝 Iterative Document Writing & Critiquing AI")
    st.markdown(f"""
        Enter an initial topic. The AI will iteratively write and critique a document.
        The loop will run for a maximum of **{loop_agent.max_iterations}** iterations.
        The final document and the last critique will be displayed.
    """)

    if ST_LOOP_RESULTS_KEY not in st.session_state:
        st.session_state[ST_LOOP_RESULTS_KEY] = None
    if ST_ERROR_KEY not in st.session_state:
        st.session_state[ST_ERROR_KEY] = None

    with st.sidebar:
        st.header("Controls")
        initial_topic_input = st.text_input(
            "Enter the initial topic for the document:",
            key=ST_TOPIC_KEY,
            placeholder="e.g., The impact of AI on creative writing"
        )

        if st.button("🔁 Run Iteration Loop", type="primary", use_container_width=True):
            if initial_topic_input:
                st.session_state[ST_LOOP_RESULTS_KEY] = None
                st.session_state[ST_ERROR_KEY] = None
                
                status_text = st.empty()
                with st.spinner("🔄 Running AI writing & critiquing loop... This may take a few moments."):
                    status_text.info("Loop initiated...")
                    try:
                        results = asyncio.run(run_loop_iterations_async(initial_topic_input))
                        st.session_state[ST_LOOP_RESULTS_KEY] = results
                        status_text.success("✅ Loop completed!")
                    except Exception as e:
                        st.session_state[ST_ERROR_KEY] = f"An error occurred during the loop: {str(e)}"
                        st.error(st.session_state[ST_ERROR_KEY]) # Display error in sidebar
                        status_text.error("❌ Loop failed.")
                        import traceback
                        print(f"Error during Streamlit run: {e}")
                        traceback.print_exc()
            else:
                st.warning("Please enter an initial topic.")
        
        st.markdown("---")
        st.caption(f"Using Model: `{GEMINI_MODEL}`")
        st.caption(f"ADK App Name: `{APP_NAME}`")
        st.caption(f"Max Iterations: `{loop_agent.max_iterations}`")

    # Main area for displaying results
    if st.session_state[ST_ERROR_KEY] and not st.session_state[ST_LOOP_RESULTS_KEY]:
        st.error(f"Loop Error: {st.session_state[ST_ERROR_KEY]}")

    if st.session_state[ST_LOOP_RESULTS_KEY]:
        results = st.session_state[ST_LOOP_RESULTS_KEY]
        
        st.subheader("🏁 Final Document")
        st.info(results.get("final_document", "No final document available."))

        st.subheader("🧐 Final Criticism")
        st.warning(results.get("final_criticism", "No final criticism available.")) # Using warning for visibility
        
    else:
        if not st.session_state[ST_ERROR_KEY]: # Initial state, no run yet
             st.info("Enter an initial topic in the sidebar and click 'Run Iteration Loop' to see the results.")

if __name__ == "__main__":
    streamlit_loop_app()