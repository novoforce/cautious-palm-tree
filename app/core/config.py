# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    GOOGLE_CLOUD_PROJECT_ID: str = "hackathon-agents"
    BIGQUERY_SERVICE_ACCOUNT_KEY_PATH: str = "hackathon-agents-044c975e8972.json"
    INTEGRATION_CONNECTOR_SERVICE_ACCOUNT_KEY_PATH: str = "hackathon-agents-f18a9f8dc92b.json"
    INTEGRATION_CONNECTOR_LOCATION: str = "us-central1"
    BQ_LOCATION: str ="us-central1"
    BQ_DATASET: str ="StyleHub"
    METADATA_JSON_PATH: str = "dataset_info.json"
    GOOGLE_API_KEY: str

    # Vector DB Settings
    VECTOR_DB_PATH: str

    # Model Settings
    MODEL_GEMINI_2_0_FLASH_LIVE: str
    GREETING_AGENT_GEMINI_MODEL: str
    BQ_AGENT_GEMINI_MODEL: str
    VISUALIZATION_AGENT_GEMINI_MODEL: str
    EMAIL_AGENT_GEMINI_MODEL: str
    POSTER_AGENT_GEMINI_MODEL: str
    IMAGE_GEN_GEMINI_MODEL: str

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

settings = Settings()

# Optional: Add a check if the service account path is relative and make it absolute
if not os.path.isabs(settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH):
    settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH = os.path.abspath(settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH)

if not os.path.isabs(settings.METADATA_JSON_PATH):
    settings.METADATA_JSON_PATH = os.path.abspath(settings.METADATA_JSON_PATH)

if not os.path.isabs(settings.INTEGRATION_CONNECTOR_SERVICE_ACCOUNT_KEY_PATH):
    settings.INTEGRATION_CONNECTOR_SERVICE_ACCOUNT_KEY_PATH = os.path.abspath(settings.INTEGRATION_CONNECTOR_SERVICE_ACCOUNT_KEY_PATH)