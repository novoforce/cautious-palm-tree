# utils.py

import os
import json
import logging
import traceback
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, GoogleCloudError
from app.core.config import settings
from typing import Dict, Any
# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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
    json_path = settings.METADATA_JSON_PATH

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
