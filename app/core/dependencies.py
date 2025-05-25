# app/core/dependencies.py
from app.services.bigquery_service import BigQueryReader
from app.core.config import settings
import functools
import logging

logger = logging.getLogger(__name__)

# Use functools.lru_cache to ensure the BigQueryReader is initialized only once
@functools.lru_cache()
def get_bigquery_reader() -> BigQueryReader:
    """
    Dependency that provides a BigQueryReader instance.
    This instance is created once and reused across all requests.
    """
    try:
        bq_reader = BigQueryReader(
            project_id=settings.GOOGLE_CLOUD_PROJECT_ID,
            service_account_key_path=settings.BIGQUERY_SERVICE_ACCOUNT_KEY_PATH
        )
        logger.info("BigQueryReader dependency successfully initialized.")
        return bq_reader
    except (FileNotFoundError, ConnectionError) as e:
        logger.critical(f"Failed to initialize BigQueryReader: {e}")
        # In a real application, you might want to raise a custom exception
        # that FastAPI can catch and return a 500 status code.
        raise # Re-raise to prevent the application from starting if critical dependency fails
    except Exception as e:
        logger.critical(f"An unexpected error occurred during BigQueryReader initialization: {e}")
        raise