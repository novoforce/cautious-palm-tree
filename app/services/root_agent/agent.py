import asyncio
import uuid
import os
from typing import Dict, Any

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.genai.types import Content, Part
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from dotenv import load_dotenv
from pydantic import BaseModel
from app.services.chat_agent.agent import call_chat_agent
from app.services.bq_agent.agent import call_bq_agent
from app.services.visualization_agent.agent import call_visualization_agent
from app.services.poster_agent.agent import call_poster_agent
from app.services.email_agent.agent import call_email_agent
from app.core.config import settings
from .prompt import SUPERVISOR_INSTRUCTIONS, GLOBAL_INSTRUCTION, SUPERVISOR_DESCRIPTION, SUPERVISOR_INSTRUCTIONS2, SUPERVISOR_INSTRUCTIONS3
# --- Constants ---
APP_NAME = "code_pipeline_module_app"
USER_ID = "dev_user_01"



def add(a: int, b: int) -> dict:
    """Adds two numbers together.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        dict: The result of the addition.
    """
    return {
        "status": "success",
        "result": a + b
    }

def subtract(a: int, b: int) -> dict:
    """Subtracts the second number from the first number.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        dict: The result of the subtraction.
    """
    return {
        "status": "success",
        "result": a - b
    }

def multiply(a: int, b: int) -> dict:
    """Multiplies two numbers together.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        dict: The result of the multiplication.
    """
    return {
        "status": "success",
        "result": a * b
    }

def divide(a: int, b: int) -> dict:
    """Divides the first number by the second number.

    Args:
        a (int): The first number.
        b (int): The second number.

    Returns:
        dict: The result of the division.
    """
    if b == 0:
        return {
            "status": "error",
            "message": "Division by zero is not allowed."
        }
    return {
        "status": "success",
        "result": a / b
    }

supervisor = LlmAgent(
    name="Supervisor",
    model=settings.MODEL_GEMINI_2_0_FLASH_LIVE, #"gemini-2.0-flash-live-001", # Use a consistent and available model
    global_instruction=GLOBAL_INSTRUCTION,
    instruction=SUPERVISOR_INSTRUCTIONS3,
    description=SUPERVISOR_DESCRIPTION,
    tools=[
           call_chat_agent,
           call_bq_agent,
           call_visualization_agent,
           call_poster_agent,
           call_email_agent], 
)
