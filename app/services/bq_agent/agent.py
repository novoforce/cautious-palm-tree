import asyncio
import uuid
import os
import json
from typing import Dict, Any

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai.types import Content, Part
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, GoogleCloudError
from dotenv import load_dotenv
import logging
import traceback

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Constants ---
APP_NAME = "sql_pipeline_app"
USER_ID = "dev_user_01"
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash-001"

# ==============================================================================
# YOUR HELPER FUNCTIONS AND CLASSES (Unchanged)
# ==============================================================================

def json_to_paragraphs(file_path):
    # TODO: Consider loading this data once at startup instead of on every run.
    with open(file_path, 'r') as file:
        data = json.load(file)
    paragraphs = []
    for table in data.get('tables', []):
        table_name = table.get('table_name', 'Unnamed Table')
        table_description = table.get('table_description', 'No description available.')
        paragraph = f"Table '{table_name}': {table_description}\n"
        paragraph += "Columns:\n"
        for column in table.get('columns', []):
            column_name = column.get('column_name', 'Unnamed Column')
            column_type = column.get('column_type', 'Unknown Type')
            column_description = column.get('column_description', 'No description available.')
            is_primary_key = column.get('is_primary_key', False)
            primary_key_info = " (Primary Key)" if is_primary_key else ""
            foreign_key_info = ""
            if 'foreign_key' in column:
                fk_table = column['foreign_key'].get('reference_table', 'Unknown Table')
                fk_column = column['foreign_key'].get('reference_column', 'Unknown Column')
                foreign_key_info = f" (Foreign Key references {fk_table}.{fk_column})"
            paragraph += f"  - {column_name} ({column_type}): {column_description}{primary_key_info}{foreign_key_info}\n"
        paragraphs.append(paragraph)
    return "\n".join(paragraphs)

def bigquery_metdata_extraction_tool():
    """ Extracts BigQuery table metadata from a JSON file."""
    # TODO: Replace hardcoded path with environment variable or configuration.
    json_path = r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\dataset_info.json"
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Metadata JSON file not found at: {json_path}")
    return json_to_paragraphs(json_path)

class BigQueryReader:
    """A class to encapsulate BigQuery read operations."""
    def __init__(self, project_id: str, service_account_key_path: str):
        if not os.path.exists(service_account_key_path):
            logger.error(f"Service account key file not found at: {service_account_key_path}")
            raise FileNotFoundError(f"Service account key not found at: {service_account_key_path}")
        self.project_id = project_id
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_key_path
        try:
            self.client = bigquery.Client(project=self.project_id)
            logger.info(f"BigQuery client successfully initialized for project: {self.client.project}")
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
            raise ConnectionError(f"Could not connect to BigQuery. Check credentials. Error: {e}")

    def execute_query(self, query: str) -> Any:
        """Executes a SQL query and returns results or an error string."""
        logger.info(f"Executing BigQuery query: {query[:100]}...")
        try:
            query_job = self.client.query(query)
            results = query_job.result()
            rows = [dict(row) for row in results]
            logger.info(f"Query executed successfully. Fetched {len(rows)} rows.")
            return rows
        except Exception:
            error_message = f"Error during query execution: {traceback.format_exc()}"
            logger.error(error_message)
            return {"error": error_message}

# Initialize the BigQuery reader tool.
# TODO: Replace hardcoded paths with environment variables for better security and portability.
SERVICE_ACCOUNT_PATH = r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\hackathon-agents-044c975e8972.json"
bq_reader = BigQueryReader(project_id="hackathon-agents", service_account_key_path=SERVICE_ACCOUNT_PATH)

# ==============================================================================
# YOUR AGENT DEFINITIONS (Unchanged, but with added context)
# ==============================================================================

def initialize_state_var(callback_context: CallbackContext):
    """Callback to initialize the session state before the pipeline runs."""
    callback_context.state["PROJECT"] = "hackathon-agents"
    callback_context.state["BQ_LOCATION"] = "us-central1"
    callback_context.state["DATASET"] = "StyleHub"
    # This pre-loads the metadata so the agents can use it.
    callback_context.state["bigquery_metadata"] = bigquery_metdata_extraction_tool()
    logger.info("Session state initialized with BigQuery project, location, and metadata.")

# Agent 1: Understands the user's query
query_understanding_agent = LlmAgent(
    name="query_understanding_agent",
    model=MODEL_GEMINI_2_0_FLASH,
    instruction="""
    You are a data analyst. Your role is to understand the user's natural language query.
    Identify the BigQuery tables and columns needed to answer the query.
    If the query is ambiguous, ask clarifying questions.
    Use the provided BigQuery metadata: {bigquery_metadata}
    Format the output as a JSON object with table.column as keys and your reasoning as values.
    """,
    output_key="query_understanding_output"
)

# Agent 2: Generates the initial SQL query
query_generation_agent = LlmAgent(
    name="query_generation_agent",
    model=MODEL_GEMINI_2_0_FLASH,
    instruction="""
    You are a BigQuery SQL writer. Your job is to write standard BigQuery SQL.
    - Use the analysis from the previous agent: {query_understanding_output}
    - Use project '{PROJECT}', location '{BQ_LOCATION}', and dataset '{DATASET}'.
    - Use the following metadata: <METADATA>{bigquery_metadata}</METADATA>
    Output only the generated query as a raw text string.
    """,
    output_key="query_generation_output"
)

# Agent 3: Reviews and refactors the SQL
query_review_rewrite_agent = LlmAgent(
    name="query_review_agent",
    model=MODEL_GEMINI_2_0_FLASH,
    instruction="""
    You are a BigQuery SQL reviewer and rewriter.
    - Original analysis: {query_understanding_output}
    - Initial query: {query_generation_output}
    - Use project '{PROJECT}', location '{BQ_LOCATION}', dataset '{DATASET}'.
    - Use metadata: {bigquery_metadata}
    Review and rewrite the query based on these rules:
    - Ensure all columns have proper aliases.
    - Add 'LIMIT 10' to SELECT queries that might fetch many records.
    - Ensure filter conditions are case-insensitive (e.g., use LOWER() or UPPER()).
    - Convert datetime/timestamp columns to strings for display.
    Output only the final, rewritten query as a raw text string.
    """,
    output_key="query_review_rewrite_output"
)

# Agent 4: Executes the query
# This agent's primary job is to format the input for the tool call.
query_execution_agent = LlmAgent(
    name="query_execution_agent",
    model=MODEL_GEMINI_2_0_FLASH,
    instruction="""
    You are a BigQuery SQL executor.
    You must execute the provided SQL query using the `execute_query` tool.
    The query to execute is: {query_review_rewrite_output}
    """,
    tools=[bq_reader.execute_query],
    output_key="query_execution_output"
)

# The complete sequential pipeline
sql_pipeline_agent = SequentialAgent(
    name="SQLPipelineAgent",
    sub_agents=[
        query_understanding_agent,
        query_generation_agent,
        query_review_rewrite_agent,
        query_execution_agent,
    ],
    before_agent_callback=initialize_state_var,
)

# Session Service Setup
_session_service = InMemorySessionService()

# ==============================================================================
# WRAPPER FUNCTION TO EXECUTE THE PIPELINE
# ==============================================================================
async def execute_sql_pipeline(user_query: str) -> Dict[str, Any]:
    """
    Executes the complete SQL generation and execution pipeline asynchronously.

    Args:
        user_query (str): A natural language query about the data.
                          Example: "Show me the top 10 products by sales."

    Returns:
        dict: A dictionary containing the results from each stage of the pipeline.
    """
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        return {"error": "GOOGLE_API_KEY environment variable not found."}

    try:
        current_session_id = str(uuid.uuid4())
        print(f"▶️  Running SQL pipeline for query: '{user_query[:50]}...'")

        await _session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        runner = Runner(
            agent=sql_pipeline_agent,
            app_name=APP_NAME,
            session_service=_session_service,
        )

        initial_message = Content(role="user", parts=[Part(text=user_query)])

        async for _ in runner.run_async(
            user_id=USER_ID, session_id=current_session_id, new_message=initial_message
        ):
            pass  # Wait for the runner to complete

        session_state_data = await _session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        # Extract the output from each step using the defined output_keys
        understanding_output = session_state_data.state.get("query_understanding_output")
        generated_sql = session_state_data.state.get("query_generation_output")
        reviewed_sql = session_state_data.state.get("query_review_rewrite_output")
        execution_result = session_state_data.state.get("query_execution_output")

        print("✅ SQL pipeline completed successfully.")
        return {
            "user_query": user_query,
            "understanding": understanding_output or "Not generated.",
            "generated_sql": generated_sql or "Not generated.",
            "reviewed_sql": reviewed_sql or "Not generated.",
            "execution_result": execution_result or "Not executed.",
        }

    except Exception as e:
        print(f"❌ Pipeline failed with an error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

# --- Example Usage ---
async def main():
    """Main function to demonstrate running the SQL pipeline."""
    print("--- Running SQL Pipeline Agent ---")
    
    # IMPORTANT: Ensure you have:
    # 1. A .env file with your GOOGLE_API_KEY.
    # 2. The BigQuery Service Account JSON key at the specified path.
    # 3. The dataset_info.json file at the specified path.

    # user_input = "how many users are there?"
    user_input = "what are the products with cost price more than 100?"
    
    result = await execute_sql_pipeline(user_input)

    print("\n--- PIPELINE RESULTS ---")
    if result.get("error"):
        print(f"Error: {result['error']}")
    else:
        # Pretty print the results
        for key, value in result.items():
            print(f"\n--- {key.replace('_', ' ').upper()} ---")
            if isinstance(value, (dict, list)):
                print(json.dumps(value, indent=2))
            else:
                print(value)
    print("------------------------")


if __name__ == "__main__":
    asyncio.run(main())