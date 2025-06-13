from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, GoogleCloudError
import logging
import traceback
import os
MODEL_GEMINI_2_0_FLASH="gemini-2.0-flash-live-001"
MODEL_GEMINI_2_0_FLASH="gemini-2.0-flash-001"  # Use the latest flash model available

logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for better visibility of service operations
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def initialize_state_var(callback_context: CallbackContext):
    PROJECT = "hackathon-agents"  # Default project ID, can be overridden by environment variable
    BQ_LOCATION = "us-central1"
    DATASET =  "StyleHub"

    callback_context.state["PROJECT"] = PROJECT
    callback_context.state["BQ_LOCATION"] = BQ_LOCATION
    callback_context.state["DATASET"] =DATASET

    bigquery_metadata = bigquery_metdata_extraction_tool()

    callback_context.state["bigquery_metadata"] = bigquery_metadata

class BigQueryReader:
    """
    A class to encapsulate BigQuery read operations using a service account.
    Focuses on querying public datasets.
    """

    def __init__(self, project_id: str, service_account_key_path: str):
        """
        Initializes the BigQuery client.

        Args:
            project_id (str): Your Google Cloud Project ID. This is required for billing
                              and job execution context, even for public datasets.
            service_account_key_path (str): Path to your service account JSON key file.
        """
        if not os.path.exists(service_account_key_path):
            logger.error(
                f"Service account key file not found at: {service_account_key_path}"
            )
            raise FileNotFoundError(
                f"Service account key file not found at: {service_account_key_path}"
            )

        self.project_id = project_id
        self.service_account_key_path = service_account_key_path
        self.client = None
        self._initialize_client()
        logger.info(f"BigQueryReader initialized for project: {self.project_id}")

    def _initialize_client(self):
        """
        Internal method to set up the BigQuery client.
        Sets GOOGLE_APPLICATION_CREDENTIALS environment variable.
        """
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.service_account_key_path
            self.client = bigquery.Client(project=self.project_id)
            # Test connection by making a small request
            # self.client.list_projects(max_results=1) # A simple test if needed
            logger.info(
                f"BigQuery client successfully initialized for project: {self.client.project}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
            raise ConnectionError(
                f"Could not connect to BigQuery. Check credentials and project ID. Error: {e}"
            )

    def list_tables_in_dataset(
        self, project: str = 'bigquery-public-data', dataset_id: str= 'thelook_ecommerce', max_results: int = 10
    ) -> list:
        """
        Lists tables in a specified BigQuery dataset.
        Default project is bigquery-public-data and the default dataset is thelook_ecommerce.

        Args:
            project (str): The project ID where the dataset resides (e.g., 'bigquery-public-data').
            dataset_id (str): The ID of the dataset (e.g., 'thelook_ecommerce').
            max_results (int): Maximum number of tables to retrieve.

        Returns:
            list: A list of table IDs (strings). Returns an empty list on error.
        """
        logger.info(f"Attempting to list tables in '{project}.{dataset_id}'...")
        try:
            dataset_ref = bigquery.DatasetReference(project, dataset_id)
            tables = []
            for table_item in self.client.list_tables(
                dataset_ref, max_results=max_results
            ):
                tables.append(table_item.table_id)
            logger.info(
                f"Successfully listed {len(tables)} tables in '{project}.{dataset_id}'."
            )
            return tables
        except NotFound:
            logger.warning(
                f"Dataset '{project}.{dataset_id}' not found or inaccessible."
            )
            return []
        except GoogleCloudError as e:
            logger.error(
                f"Google Cloud Error listing tables in '{project}.{dataset_id}': {e}"
            )
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred while listing tables: {e}")
            return []

    def execute_query(self, query: str) -> tuple:
        """
        Executes a SQL query on BigQuery and returns the results.
        Default project is `bigquery-public-data` and the default dataset is `thelook_ecommerce`.

        Args:
            query (str): The SQL query string to execute.

        Returns:
            tuple: The SQL query and a list of BigQuery Row objects, or an empty list if an error occurs.
        """
        logger.info("Executing BigQuery query...")
        try:
            print("Generated sql:> ",query)
            query_job = self.client.query(query)  # API request
            results = query_job.result()  # Waits for job to complete
            rows = [
                dict(row) for row in results
            ]  # Convert rows to dictionaries for easier handling
            logger.info(f"Query executed successfully. Fetched {len(rows)} rows.")
            return (rows)
        except Exception as e:
            error_message = f"An unexpected error occurred during query execution: {e}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
        return (traceback.format_exc())

bq_reader = BigQueryReader(
            project_id="hackathon-agents",
            service_account_key_path=r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\hackathon-agents-044c975e8972.json"
        )

import json
def json_to_paragraphs(file_path):
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
    
    return paragraphs


# Agent Prompt pasted here for easy reference
QUERY_UNDERSTANDING_PROMPT_STR = """
    You are playing a data analyst role whose role is to understand the user query provided natural language text query.
    The intention is to identify the bigquery tables and columns that will be needed to answer the query query.
    If the user query is ambiguous, ask for clarifying queries.

    Use the below bigquery metadata which provides the details on tables, columns, data types and descriptions for identifying the tables/columns.
    {bigquery_metadata}

    Format the output in form of JSON with key as table.column and value as reasoning for picking the column.
"""
# LLM Agent for analysis of the user query to identify the user question and derive tables/columns involved 
query_understanding_agent = LlmAgent(
    name = "query_understanding_agent",
    model = "gemini-2.5-flash-preview-04-17",
    description = """This agent is responsible for understanding the intent of the user question 
        and identifying tables/columns involved to answer the query
    """,
    instruction = QUERY_UNDERSTANDING_PROMPT_STR,
    output_key = "query_understanding_output"
)

# Agent Prompt pasted here for easy reference
QUERY_GENERATION_INSTRUCTION_STR = """
    You are playing role of bigquery sql writer.
    Your job is write bigquery sqls in standard dialect.
    
    - Use the analysis done by the query understanding agent as below
      {query_understanding_output}

    - Use the project as {PROJECT}, location as {BQ_LOCATION}, dataset as {DATASET} for generating the bigquery queries for the user provided question.
    - Use the following metadata for understanding the tables, columns, datatypes and description of the columns.
    <METADATA START>
    {bigquery_metadata}
    <METADATA END>

    Output only the generated query as text
    """

def bigquery_metdata_extraction_tool():
    """ Extracts BigQuery table metadata from a JSON file and returns it as paragraphs."""
    json_path= r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\dataset_info.json"
    metadata= json_to_paragraphs(json_path)
    return metadata

# LLM Agent for generation of bigquery based on the analysis received from the query_understanding_agent
query_generation_agent = LlmAgent(
    name = "query_generation_agent",
    model = "gemini-2.5-flash-preview-04-17",
    description = "This agent is responsible for generating bigquery queries in standard sql dialect",
    instruction = QUERY_GENERATION_INSTRUCTION_STR,
    # tools = [bigquery_metdata_extraction_tool],  #<----Possibility of adding a tool to find out similar queries previously provided (Abhinav's idea)
    output_key = "query_generation_output"
)


QUERY_REVIEW_REWRITE_INSTRUCTION_STR = """
    You are playing role of bigquery sql reviewer and rewriter.
    Your job is review and based on the review if any rewrite bigquery sqls in standard dialect.
    
    - Use the query understanding agent output as below
      {query_understanding_output}

    - Use the query generated done by the query generation agent as below
      {query_generation_output}

    - Use the project as {PROJECT}, location as {BQ_LOCATION}, dataset as {DATASET} for generating the bigquery queries for the user provided question.
    - Use the `bigquery_metadata_extraction_tool` for metadata extraction for understanding the tables, columns, datatypes and description of the columns.
    
    Review Items
    - check if the columns have proper aliases, if not added appropriate alias
    - Add limit to 10 in case of select queries that might fetch lot of records
    - check if all columns are needed in query and bring the relevant ones
    - handle the casing of the filter conditions for matching eg: upper(state) = "OHIO" or lower(state)="ohio"
    - convert the datetime attributes to string for display purposes

    Output only the rewritten query as text
    """

# LLM Agent for review of the SQL queries and rewriting the sql queries if needed
query_review_rewrite_agent = LlmAgent(
    name = "query_review_agent",
    model = "gemini-2.5-flash-preview-04-17",
    description = f"This agent is responsible for reviewing queries in the bigquery",
    instruction = QUERY_REVIEW_REWRITE_INSTRUCTION_STR,
    output_key = "query_review_rewrite_output"
)

QUERY_EXECUTION_INSTRUCTION_STR = """
    You are playing role of bigquery sql executor.
    Your job is review and based on the review if any rewrite bigquery sqls in standard dialect.
    
    - Execute the query generated below on bigqquery using the `bq_reader.execute_query` and display the results as markdown table with proper headers
      {query_review_rewrite_output}

    """

# LLM Agent for execution of the bigquery sqls
query_execution_agent = LlmAgent(
    name = "query_execution_agent",
    model = "gemini-2.5-flash-preview-04-17",
    description = f"This agent is responsible for exeuction of queries in the bigquery and present the result as markdown table",
    instruction = QUERY_EXECUTION_INSTRUCTION_STR,
    tools = [ bq_reader.execute_query ],
    output_key = "query_execution_output"
)


sql_pipeline_agent = SequentialAgent(
    name="SQLPipelineAgent",
    sub_agents=[query_understanding_agent, query_generation_agent, query_review_rewrite_agent, query_execution_agent],
    description="Executes a sequence of code writing, reviewing, and refactoring.",
    # The agents will run in the order provided: Writer -> Reviewer -> Refactorer
    before_agent_callback=initialize_state_var,
)

#POSTER CREATION AGENT-------------------------------------------------------START>
from google.adk.tools import agent_tool
from google.adk.tools import load_artifacts
from google.adk.tools import ToolContext
from google.genai import Client
from google.genai import types
client = Client()

async def generate_image(prompt: str, tool_context: 'ToolContext'):
  """Generates an image based on the prompt."""
  response = client.models.generate_images(
      model='imagen-3.0-generate-002',
      prompt=prompt,
      config={'number_of_images': 1},
  )
  if not response.generated_images:
    return {'status': 'failed'}
  image_bytes = response.generated_images[0].image.image_bytes
  await tool_context.save_artifact(
      'image.png',
      types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
  )
  return {
      'status': 'success',
      'detail': 'Image generated successfully and stored in artifacts.',
      'filename': 'image.png',
  }
  
image_generator_agent = LlmAgent(
    model=MODEL_GEMINI_2_0_FLASH, #'gemini-2.0-flash-001',
    name='root_agent',
    description="""An agent that generates images and answer questions about the images.""",
    instruction="""You are an agent whose job is to generate or edit an image based on the user's prompt.
""",
    tools=[generate_image, load_artifacts],
)

# image_agent = generate_image()
# image_tool = agent_tool.AgentTool(agent=image_agent)
#POSTER CREATION AGENT-------------------------------------------------------END>

#GREETING AGENT-------------------------------------------------------START>
general_greeting_agent = LlmAgent(
    name="general_greeting_agent",
    model=MODEL_GEMINI_2_0_FLASH, #"gemini-2.5-flash-preview-04-17",
    description=(
        "Agent to answer questions relating to user general query"
    ),
    instruction=(
        """You are a helpful agent who can answer user questions and have a great open conversation.
        You can speak in English, Hindi, or any other language."""
    ),
)

greeting_tool = agent_tool.AgentTool(agent=general_greeting_agent)
#GREETING AGENT-------------------------------------------------------END>

#VISUALIZATION AGENT-------------------------------------------------------START>
chart_type_agent = LlmAgent(
    name="visualization_agent",
    model=MODEL_GEMINI_2_0_FLASH,#"gemini-2.5-flash-preview-04-17", #{query_understanding_output}
    description=(
        "Agent to predict the chart type and the design of the chart based on the user query and the data provided."
    ),
    instruction=(
        """You are a chart type agent who can predict the chart type and the design of the chart based on the user query and the data provided. You will be provided with the User query and the data in the form of a JSON object.
        You need to analyze the data and the user query to predict the chart type and the design of the chart. You can use the following chart types: bar, line, pie, scatter, area, histogram, boxplot, heatmap, radar, treemap, funnel, waterfall, gauge, bullet, polar, sunburst, chord, sankey.
        #User Query: "Users who ordered the most"
        #Data: ```{query_execution_output}```

        """
    ),
    output_key="chart_type_output",
)

plotly_code_agent = LlmAgent(
    name="plotly_code_agent",
    model=MODEL_GEMINI_2_0_FLASH,#"gemini-2.5-flash-preview-04-17",
    description=(
        "Agent to generate plotly code for the chart type and design predicted by the chart type agent."
    ),
    instruction=(
        """You are a plotly code agent who can generate plotly code for the chart type and design predicted by the chart type agent. You will be provided with the chart type and the design of the chart.
        You need to generate the plotly code for the chart type and the design of the chart. 
        The final plotly code should save the chart as a PNG image and return the image path.
        #Chart Type: ```{chart_type_output}```
        #Data: ```{query_execution_output}```
"""
),
    output_key="plotly_code_output",
)

    
import plotly.graph_objects as go
import plotly.io as pio

async def execute_plotly_code_and_get_image_bytes(plotly_code_str: str,tool_context: 'ToolContext'):
    # Create a local dictionary to execute the code
    local_vars = {}
    # Execute the Plotly code string
    exec(plotly_code_str, {}, local_vars)
    # Extract the figure object
    fig = local_vars.get('fig')
    if fig is None or not isinstance(fig, go.Figure):
        raise ValueError("The Plotly code must define a Plotly figure object named 'fig'.")
    # Get the image bytes
    image_bytes = pio.to_image(fig, format='png')
    await tool_context.save_artifact(
      'plot.png',
      types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
  )
    return {
      'status': 'success',
      'detail': 'Image generated successfully and stored in artifacts.',
      'filename': 'plot.png',
  }

plotly_code_executor_agent = LlmAgent(
    model=MODEL_GEMINI_2_0_FLASH,#'gemini-2.0-flash-001',
    name='plotly_code_executor_agent',
    description="""An agent that executes Plotly code and generates an image from it.""",
    instruction="""Use `execute_plotly_code_and_get_image_bytes` tool to execute the Plotly code and generate an image.
    
""",
    tools=[execute_plotly_code_and_get_image_bytes, load_artifacts],
)

visualization_agent = SequentialAgent(
    name="visualization_agent",
    sub_agents=[chart_type_agent, plotly_code_agent, plotly_code_executor_agent],
    description="Executes a sequence of chart type prediction, plotly code generation, and image generation.",
    # instruction="""This agent is responsible for generating visualizations based on user queries."""
    # The agents will run in the order provided: Chart Type -> Plotly Code -> Image Generation
    # before_agent_callback=initialize_state_var,
)



# Below is a working example but fails in authentication:> 
from google.adk.tools.application_integration_tool.application_integration_toolset import ApplicationIntegrationToolset
sa_key_file_path =r"D:\3_hackathon\1_llm_agent_hackathon_google\cautious-palm-tree\rough_work_scripts\hackathon-agents-f18a9f8dc92b.json"

# Read the entire file content into a string
with open(sa_key_file_path, 'r') as f:
    sa_key_string = f.read()
    print("key:> ",sa_key_string)



email_tool = ApplicationIntegrationToolset(
    project="hackathon-agents", # TODO: replace with GCP project of the connection
    location="us-central1", #TODO: replace with location of the connection
    integration="sendEmailAshish", #TODO: replace with integration name
    triggers=["api_trigger/sendEmailAshish_API_1"],#TODO: replace with trigger id(s). Empty list would mean all api triggers in the integration to be considered. 
    service_account_json=sa_key_string, #optional. Stringified json for service account key
    tool_name_prefix="send email",
    tool_instructions="Use this tool to send email using the integration",
)

email_agent = LlmAgent(
    model=MODEL_GEMINI_2_0_FLASH,#'gemini-2.0-flash',
    name='connector_agent',
    instruction="Use `email_tool` to send emails.",
    tools=[email_tool],
)

coordinator = LlmAgent(
    name="HelpDeskCoordinator",
    model=MODEL_GEMINI_2_0_FLASH,#"gemini-2.5-flash-preview-04-17",
    instruction="""
    You are an intelligent agent who routes the requests to the appropriate sub-agents based on the user query.
    Your primary task is to route the requests to the appropriate sub-agents based on the user query.
    You will receive a user query and you need to analyze it to determine the best sub-agent to handle it.
    You can use the following sub-agents to handle different types of requests:
    'sql_pipeline_agent': Handles SQL query generation, review, and execution.
    'image_generator_agent' tool: Handles image generation requests.
    'greeting_tool': Handles general user queries and greetings.
    'email_agent': Handles email sending requests from the user.
    'visualization_agent': Handles data visualization requests.
    You should analyze the user query and determine which sub-agent is best suited to handle it.
    
    """,
    description="Main Customer data platform(CDP) help desk router.",
    tools = [greeting_tool],
    sub_agents=[sql_pipeline_agent, image_generator_agent, visualization_agent, email_agent]
)

# For ADK tools compatibility, the root agent must be named `root_agent`
root_agent = coordinator #<--------------------------------------important to note that this is the root agent for ADK tools compatibility