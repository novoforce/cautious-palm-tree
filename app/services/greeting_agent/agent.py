from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, GoogleCloudError
from app.core.config import settings
import logging
import traceback
import os
from google.genai import types
from google.adk.models import Gemini
# llm = Gemini(
#     model_name="gemini-2.0-flash-live-001",
#     api_key="AIzaSyDlgYyela8FxcG0pJCaxD7D3Y64F37jzXA",
#     generate_content_config=types.HttpOptions(api_version='v1alpha')
# )

general_greeting_agent = LlmAgent(
    name="general_greeting_agent",
    model="gemini-2.0-flash-001", #"gemini-2.5-flash-preview-04-17",
    description=(
        "Agent to answer questions relating to user general query"
    ),
    instruction=(
        """You are a helpful agent who can answer user questions and have a great open conversation.
        You can speak in English, Hindi, or any other language."""
    ),
    
)