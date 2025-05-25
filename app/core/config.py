# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    GOOGLE_CLOUD_PROJECT_ID: str = "hackathon-agents" # Default, but better to set via env var
    BIGQUERY_SERVICE_ACCOUNT_KEY_PATH: str = "hackathon-agents-044c975e8972.json"
    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

settings = Settings()

# Optional: Add a check if the service account path is relative and make it absolute
if not os.path.isabs(settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH):
    settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH = os.path.abspath(settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH)