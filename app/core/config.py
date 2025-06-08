# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    GOOGLE_CLOUD_PROJECT_ID: str = "hackathon-agents" # Default, but better to set via env var
    BIGQUERY_SERVICE_ACCOUNT_KEY_PATH: str = "hackathon-agents-044c975e8972.json"
    A2A_TELL_TIME_AGENT_URL: str = "http://localhost:10000" # Default, from your A2A sample
    A2A_GREETING_AGENT_URL: str = "http://localhost:10001" # Default, from your A2A sample
    # If you were to run the A2A HostAgent, its URL would go here too
    # A2A_HOST_AGENT_URL: str = "http://localhost:10002"
    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

settings = Settings()

# Optional: Add a check if the service account path is relative and make it absolute
if not os.path.isabs(settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH):
    settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH = os.path.abspath(settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH)