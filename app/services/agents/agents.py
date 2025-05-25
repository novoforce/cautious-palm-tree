from google.adk.agents import Agent
from app.core.dependencies import get_bigquery_reader

bq_rdr= get_bigquery_reader()
# from app.services.agents.agents_tools import (
#     create_event,
#     delete_event,
#     edit_event,
#     get_current_time,
#     list_events,)

MODEL_GEMINI_2_0_FLASH="gemini-2.0-flash-live-001" #"gemini-2.0-flash-exp" # Example model name, replace with actual model name
general_agent = Agent(
    # A unique name for the agent.
    name="jarvis",
    model=MODEL_GEMINI_2_0_FLASH,
    description="General conversation agent",
    instruction=f"""
    You are Jarvis, a helpful assistant that can speak with user and have a healthy conversation. 
    You will asked about the queries related to the database. Use appropriate tools provided to answer the user queries.
    Please use the following format to create SQL's which is Bigquery compatible.
    
    For example:
        User query:> "How many users are there in the dataset?"
        SQL query:> SELECT count(*) FROM bigquery-public-data.thelook_ecommerce.users
    
    Try to end the conversation in a positive note.
    """,
    tools=[bq_rdr.execute_query, bq_rdr.list_tables_in_dataset]
)