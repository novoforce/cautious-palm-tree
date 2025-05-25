from google.adk.agents import Agent

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
    You are Jarvis, a helpful assistant that can speak with user and have a healthy conversation. Try to end the conversation in a positive note
    """,
)