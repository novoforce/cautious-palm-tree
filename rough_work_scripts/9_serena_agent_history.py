import streamlit as st
import asyncio
import uuid  # For unique session IDs
import os
import json
import logging
import traceback

# ADK and Google Cloud Imports
from google.adk.artifacts import InMemoryArtifactService
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai.types import Content, Part
from google.adk.agents.callback_context import CallbackContext
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, GoogleCloudError
from google.adk.tools import agent_tool, ToolContext, load_artifacts
from google.genai import Client
from google.adk.tools.application_integration_tool.application_integration_toolset import (
    ApplicationIntegrationToolset,
)

# Visualization Imports
import plotly.graph_objects as go
import plotly.io as pio

# --- Environment and Logging Setup ---
MODEL_GEMINI_FLASH = "gemini-2.0-flash-001"
# IMPORTANT: Replace these dummy paths with your actual file paths
SA_KEY_PATH = r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\hackathon-agents-044c975e8972.json"
DATASET_INFO_PATH = (
    r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\dataset_info.json"
)
EMAIL_SA_KEY_PATH = r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\rough_work_scripts\hackathon-agents-f18a9f8dc92b.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ==============================================================================
# AGENT AND TOOL DEFINITIONS (UNCHANGED)
# ==============================================================================


# --- BigQuery Tools and Metadata Functions ---
def initialize_state_var(callback_context: CallbackContext):
    PROJECT = "hackathon-agents"
    BQ_LOCATION = "us-central1"
    DATASET = "StyleHub"
    callback_context.state["PROJECT"] = PROJECT
    callback_context.state["BQ_LOCATION"] = BQ_LOCATION
    callback_context.state["DATASET"] = DATASET
    if os.path.exists(DATASET_INFO_PATH):
        bigquery_metadata = bigquery_metdata_extraction_tool(DATASET_INFO_PATH)
        callback_context.state["bigquery_metadata"] = bigquery_metadata
    else:
        callback_context.state["bigquery_metadata"] = (
            f"Error: Dataset info JSON not found at {DATASET_INFO_PATH}."
        )


class BigQueryReader:
    def __init__(self, project_id: str, service_account_key_path: str):
        if not service_account_key_path or not os.path.exists(service_account_key_path):
            raise FileNotFoundError(
                f"Service account key file not found at path: {service_account_key_path}"
            )
        self.project_id = project_id
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_key_path
        try:
            self.client = bigquery.Client(project=self.project_id)
            logger.info(
                f"BigQuery client successfully initialized for project: {self.client.project}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
            raise ConnectionError(
                f"Could not connect to BigQuery. Check credentials and project ID. Error: {e}"
            )

    def execute_query(self, query: str) -> tuple:
        logger.info(f"Executing BigQuery query: {query}")
        try:
            query_job = self.client.query(query)
            results = query_job.result()
            rows = [dict(row) for row in results]
            logger.info(f"Query executed successfully. Fetched {len(rows)} rows.")
            return rows
        except Exception as e:
            logger.error(f"An unexpected error during query execution: {e}")
            return traceback.format_exc()


def json_to_paragraphs(file_path):
    with open(file_path, "r") as file:
        data = json.load(file)
    paragraphs = []
    for table in data.get("tables", []):
        p = f"Table '{table.get('table_name')}': {table.get('table_description')}\nColumns:\n"
        for col in table.get("columns", []):
            p += f"  - {col.get('column_name')}: {col.get('column_description')}\n"
        paragraphs.append(p)
    return "\n".join(paragraphs)


def bigquery_metdata_extraction_tool(json_path: str):
    return json_to_paragraphs(json_path)


QUERY_UNDERSTANDING_PROMPT_STR = """You are a data analyst. Understand the user query to identify the bigquery tables and columns needed to answer it. Use the provided metadata. If the query is ambiguous, ask for clarification.
{bigquery_metadata}
Format the output as a JSON object with 'table.column' as key and reasoning as value."""
query_understanding_agent = LlmAgent(
    name="query_understanding_agent",
    model=MODEL_GEMINI_FLASH,
    description="Understands user query and identifies tables/columns.",
    instruction=QUERY_UNDERSTANDING_PROMPT_STR,
    output_key="query_understanding_output",
)

QUERY_GENERATION_INSTRUCTION_STR = """You are a BigQuery SQL writer. Write a standard SQL query based on the user's question and the analysis from the understanding agent.
- Analysis: {query_understanding_output}
- Project: {PROJECT}, Location: {BQ_LOCATION}, Dataset: {DATASET}
- Metadata: {bigquery_metadata}
Output only the generated query as text."""
query_generation_agent = LlmAgent(
    name="query_generation_agent",
    model=MODEL_GEMINI_FLASH,
    description="Generates BigQuery SQL queries.",
    instruction=QUERY_GENERATION_INSTRUCTION_STR,
    output_key="query_generation_output",
)

QUERY_REVIEW_REWRITE_INSTRUCTION_STR = """You are a BigQuery SQL reviewer and rewriter. Review the given SQL query and rewrite it if necessary based on best practices.
- Analysis: {query_understanding_output}
- Original Query: {query_generation_output}
- Metadata from `bigquery_metadata_extraction_tool`
- Review Items: Check for aliases, add LIMIT 10 to broad SELECTs, ensure only relevant columns are selected, handle filter casing (e.g., use LOWER()), convert datetimes to strings for display.
Output only the final, rewritten query as text."""
query_review_rewrite_agent = LlmAgent(
    name="query_review_agent",
    model=MODEL_GEMINI_FLASH,
    description="Reviews and rewrites BigQuery SQL.",
    instruction=QUERY_REVIEW_REWRITE_INSTRUCTION_STR,
    output_key="query_review_rewrite_output",
)

QUERY_EXECUTION_INSTRUCTION_STR = """You are a BigQuery SQL executor.
- Execute the following query using the `execute_query` tool:
{query_review_rewrite_output}
- After executing, present the results as a markdown table with proper headers."""
query_execution_agent = LlmAgent(
    name="query_execution_agent",
    model=MODEL_GEMINI_FLASH,
    description="Executes BigQuery queries and formats results.",
    instruction=QUERY_EXECUTION_INSTRUCTION_STR,
    output_key="query_execution_output",
)

sql_pipeline_agent = SequentialAgent(
    name="SQLPipelineAgent",
    sub_agents=[
        query_understanding_agent,
        query_generation_agent,
        query_review_rewrite_agent,
        query_execution_agent,
    ],
    description="A pipeline to understand a user's data question, generate a SQL query, review it, and execute it.",
    before_agent_callback=initialize_state_var,
)


# --- Image Generation Agent ---
client = Client()


async def generate_image(prompt: str, tool_context: "ToolContext"):
    response = client.models.generate_images(
        model="imagen-3.0-generate-002", prompt=prompt
    )
    if not response.generated_images:
        return {"status": "failed"}
    image_bytes = response.generated_images[0].image.image_bytes
    await tool_context.save_artifact(
        "image.png", Part.from_bytes(data=image_bytes, mime_type="image/png")
    )
    return {"status": "success", "filename": "image.png"}


image_generator_agent = LlmAgent(
    model=MODEL_GEMINI_FLASH,
    name="image_generator_agent",
    description="Generates images from a prompt.",
    instruction="Use `generate_image` to create an image.",
    tools=[generate_image, load_artifacts],
)

# --- Greeting Agent ---
general_greeting_agent = LlmAgent(
    name="general_greeting_agent",
    model=MODEL_GEMINI_FLASH,
    description="Handles general conversation.",
    instruction="You are a helpful conversational agent.",
)
greeting_tool = agent_tool.AgentTool(agent=general_greeting_agent)

chart_type_agent = LlmAgent(
    name="chart_type_agent",
    model=MODEL_GEMINI_FLASH,
    description="Predicts the best chart type based on user query and data.",
    instruction="""Analyze the user query and data to predict the best chart type (e.g., bar, line, pie). User Query: "{user_query}" Data: ```{query_execution_output}```""",
    output_key="chart_type_output",
)

plotly_code_agent = LlmAgent(
    name="plotly_code_agent",
    model=MODEL_GEMINI_FLASH,
    description="Generates Plotly code for a given chart type and data.",
    instruction="""Generate Python code using the Plotly library to create a chart. The code should render the final chart as the image. The code must define a figure object named 'fig'. Chart Type: ```{chart_type_output}``` Data: ```{query_execution_output}```""",
    output_key="plotly_code_output",
)


async def execute_plotly_code_and_get_image_bytes(
    plotly_code_str: str, tool_context: ToolContext
):
    local_vars = {"go": go, "json": json}
    try:
        exec(plotly_code_str, globals(), local_vars)
        fig = local_vars.get("fig")
        if fig and isinstance(fig, go.Figure):
            image_bytes = pio.to_image(fig, format="png")
            await tool_context.save_artifact(
                "plot.png", Part.from_bytes(data=image_bytes, mime_type="image/png")
            )
            return {"status": "success", "filename": "plot.png"}
        else:
            return {
                "status": "error",
                "detail": "Plotly code did not produce a figure object named 'fig'.",
            }
    except Exception as e:
        return {"status": "error", "detail": f"Error executing plotly code: {str(e)}"}


plotly_code_executor_agent = LlmAgent(
    model=MODEL_GEMINI_FLASH,
    name="plotly_code_executor_agent",
    description="Executes Plotly code.",
    instruction="Use `execute_plotly_code_and_get_image_bytes` to run the code: {plotly_code_output}",
    tools=[execute_plotly_code_and_get_image_bytes, load_artifacts],
)

visualization_agent = SequentialAgent(
    name="visualization_agent",
    sub_agents=[chart_type_agent, plotly_code_agent, plotly_code_executor_agent],
    description="Pipeline to create a data visualization.",
)

# --- Email Agent ---
email_agent = LlmAgent(
    model=MODEL_GEMINI_FLASH,
    name="email_agent",
    description="Sends emails.",
    instruction="Use the tool to send emails.",
)

coordinator = LlmAgent(
    name="HelpDeskCoordinator",
    model=MODEL_GEMINI_FLASH,
    instruction="""You are an intelligent coordinator agent. Your primary task is to understand a user's request and route it to the correct sub-agent or tool.
    - For SQL queries or data questions ('who are the top customers', 'show me sales data'), use 'sql_pipeline_agent'.
    - For creating images from a description ('draw a picture of a cat'), use 'image_generator_agent'.
    - For creating charts or graphs from data ('visualize the results'), use 'visualization_agent'.
    - For sending emails ('email this to ...'), use 'email_agent'.
    - For general conversation, greetings, or questions you can't handle, use 'greeting_tool'.
    """,
    description="Main customer help desk router that directs tasks to specialized agents.",
    tools=[greeting_tool],
    sub_agents=[
        sql_pipeline_agent,
        image_generator_agent,
        visualization_agent,
        email_agent,
    ],
)

root_agent = coordinator

# ==============================================================================
# AGENT RUNNER LOGIC (UNCHANGED)
# ==============================================================================


async def run_root_agent(
    query: str,
    session_id: str,
    session_service: InMemorySessionService,
    artifact_service: InMemoryArtifactService,
    is_new_session: bool,
):
    app_name = "cdp_help_desk"
    user_id = "dev_user"

    try:
        # Check if paths exist before proceeding
        if not os.path.exists(SA_KEY_PATH):
            raise FileNotFoundError(f"SA Key for BigQuery not found at: {SA_KEY_PATH}")
        if not os.path.exists(EMAIL_SA_KEY_PATH):
             raise FileNotFoundError(f"SA Key for Email not found at: {EMAIL_SA_KEY_PATH}")

        bq_reader = BigQueryReader(
            project_id="hackathon-agents", service_account_key_path=SA_KEY_PATH
        )
        query_execution_agent.tools = [bq_reader.execute_query]
        with open(EMAIL_SA_KEY_PATH, "r") as f:
            sa_key_string = f.read()
        email_tool = ApplicationIntegrationToolset(
            project="hackathon-agents",
            location="us-central1",
            integration="sendEmailAshish",
            triggers=["api_trigger/sendEmailAshish_API_1"],
            service_account_json=sa_key_string,
        )
        email_agent.tools = [email_tool]
    except Exception as e:
        logger.error(f"Failed to initialize tools: {e}")
        raise

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        artifact_service=artifact_service,
    )

    if is_new_session:
        logger.info(f"Creating new ADK session in service: {session_id}")
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state={"user_query": query},
        )

    existing_artifact_keys = set(await artifact_service.list_artifact_keys(
        app_name=app_name, user_id=user_id, session_id=session_id
    ))

    initial_message = Content(role="user", parts=[Part(text=query)])

    final_responses = []
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=initial_message
    ):
        if event.is_final_response():
            if event.content and event.content.parts and event.content.parts[0].text:
                final_responses.append(event.content.parts[0].text)

    final_response_text = (
        "\n\n".join(final_responses)
        if final_responses
        else "Agent finished without a text response."
    )

    all_artifact_keys = set(await artifact_service.list_artifact_keys(
        app_name=app_name, user_id=user_id, session_id=session_id
    ))
    new_artifact_keys = all_artifact_keys - existing_artifact_keys

    newly_loaded_artifacts = {}
    if new_artifact_keys:
        logger.info(f"Found new artifacts for this turn: {new_artifact_keys}")
        for key in new_artifact_keys:
            artifact_part = await artifact_service.load_artifact(
                app_name=app_name, user_id=user_id, session_id=session_id, filename=key
            )
            if artifact_part:
                newly_loaded_artifacts[key] = artifact_part

    session_state_data = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    return {
        "final_response": final_response_text,
        "full_session_state": session_state_data.state,
        "artifacts": newly_loaded_artifacts,
    }


# ==============================================================================
# NEW AND MODIFIED STREAMLIT UI
# ==============================================================================

# --- NEW: Session Management Callbacks ---

def save_current_session():
    """Saves the current session's messages to the session_history."""
    if st.session_state.messages: # Only save if there are messages
        st.session_state.session_history[st.session_state.adk_session_id] = {
            "messages": st.session_state.messages
        }

def start_new_session():
    """Clears the current session and starts a new one."""
    save_current_session()
    st.session_state.adk_session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.latest_agent_state = {}
    st.session_state.adk_session_created = False
    # No need to rerun, Streamlit reruns on widget interaction

def load_session(session_id_to_load):
    """Loads a previous session from the history."""
    save_current_session()
    st.session_state.adk_session_id = session_id_to_load
    st.session_state.messages = st.session_state.session_history[session_id_to_load]["messages"]
    st.session_state.latest_agent_state = {} # Clear transient state log
    st.session_state.adk_session_created = True # The session already exists


def display_event_log(session_state):
    """Helper function to display agent events in the sidebar."""
    st.sidebar.header("Agent Events Log (Current Turn)")
    if not session_state:
        st.sidebar.info("No agent activity to display yet.")
        return

    event_keys = [
        "bigquery_metadata", "query_understanding_output", "query_generation_output",
        "query_review_rewrite_output", "query_execution_output",
        "chart_type_output", "plotly_code_output",
    ]

    for key in event_keys:
        if key in session_state and session_state[key]:
            with st.sidebar.expander(f"Event: `{key}`", expanded=False):
                content = session_state[key]
                if isinstance(content, str) and (content.strip().startswith("{") or content.strip().startswith("[")):
                    try:
                        st.json(json.loads(content))
                    except json.JSONDecodeError:
                        st.code(content, language="sql" if "query" in key else "text")
                elif isinstance(content, list):
                    st.json(content)
                else:
                    st.markdown(f"```\n{str(content)}\n```")


def streamlit_app():
    st.set_page_config(layout="wide", page_title="AI Agent Coordinator")

    # --- MODIFIED: Session State Initialization ---
    if "adk_session_id" not in st.session_state:
        st.session_state.adk_session_id = str(uuid.uuid4())
        st.session_state.session_service = InMemorySessionService()
        st.session_state.artifact_service = InMemoryArtifactService()
        st.session_state.adk_session_created = False
        st.session_state.messages = []
        st.session_state.latest_agent_state = {}
        # NEW: Add session_history to store all conversations
        st.session_state.session_history = {}


    # --- NEW: Sidebar for Session Management ---
    with st.sidebar:
        st.title("Session Management")
        st.button("➕ New Chat", on_click=start_new_session, use_container_width=True)
        st.divider()

        st.header("Session History")
        # Display sessions in reverse chronological order (newest on top)
        history_ids = list(st.session_state.session_history.keys())
        for session_id in reversed(history_ids):
            session_messages = st.session_state.session_history[session_id]["messages"]
            # Find the first user message to use as a title, or default
            first_user_message = next((m['content'] for m in session_messages if m['role'] == 'user'), "Chat")
            label = f"{first_user_message[:35]}..." if len(first_user_message) > 35 else first_user_message
            
            # Use a unique key for each button
            st.button(
                label,
                key=f"btn_{session_id}",
                on_click=load_session,
                args=(session_id,),
                use_container_width=True,
                disabled=(session_id == st.session_state.adk_session_id) # Disable button for active session
            )
        st.divider()
        display_event_log(st.session_state.latest_agent_state)


    # --- Main Content: Chat Interface ---
    st.title("🤖 AI Agent Help Desk")
    st.caption(f"Active Session ID: {st.session_state.adk_session_id}")
    st.markdown(
        """
        This is an interactive chat with an AI coordinator. Ask it to perform tasks like:
        - `Show me the top 5 users by number of orders.`
        - `Now, visualize these results as a bar chart.`
        - `Draw a picture of a futuristic storefront.`
        - `Email the chart to example@example.com`
    """
    )
    st.divider()

    # Display existing messages in the chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and "artifacts" in message and message["artifacts"]:
                with st.expander("🖼️ View Generated Content", expanded=False):
                    image_artifacts = [
                        (filename, part)
                        for filename, part in message["artifacts"].items()
                        if "image" in part.inline_data.mime_type
                    ]
                    if image_artifacts:
                        cols = st.columns(len(image_artifacts))
                        for i, (filename, part) in enumerate(image_artifacts):
                            with cols[i]:
                                st.image(part.inline_data.data, caption=filename)

    # Chat input for user's new prompt
    if prompt := st.chat_input("What would you like to do?"):
        # Add user message to chat history and display it
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Process the request with the agent
        with st.chat_message("assistant"):
            with st.spinner("🧠 The agent is thinking..."):
                try:
                    is_new = not st.session_state.adk_session_created
                    results = asyncio.run(
                        run_root_agent(
                            query=prompt,
                            session_id=st.session_state.adk_session_id,
                            session_service=st.session_state.session_service,
                            artifact_service=st.session_state.artifact_service,
                            is_new_session=is_new,
                        )
                    )
                    st.session_state.adk_session_created = True

                    response_text = results.get("final_response", "I have completed the task.")
                    artifacts = results.get("artifacts", {})
                    st.session_state.latest_agent_state = results.get("full_session_state", {})

                    st.markdown(response_text)

                    if artifacts:
                        with st.expander("🖼️ View Generated Content", expanded=True):
                            image_artifacts = [
                                (filename, part)
                                for filename, part in artifacts.items()
                                if "image" in part.inline_data.mime_type
                            ]
                            if image_artifacts:
                                cols = st.columns(len(image_artifacts))
                                for i, (filename, part) in enumerate(image_artifacts):
                                    with cols[i]:
                                        st.image(part.inline_data.data, caption=filename)

                    # Store the complete response in history
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": response_text,
                            "artifacts": artifacts,
                        }
                    )
                    st.rerun()

                except Exception as e:
                    error_message = f"An error occurred: {str(e)}\n\n{traceback.format_exc()}"
                    st.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})


if __name__ == "__main__":
    streamlit_app()