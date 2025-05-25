# app/services/bigquery_service.py
import os
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, GoogleCloudError
import logging

# Configure logging for better visibility within the service
# Note: FastAPI will handle global logging usually, but this is good for internal service logs.
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for better visibility of service operations
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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
        self, project: str, dataset_id: str, max_results: int = 10
    ) -> list:
        """
        Lists tables in a specified BigQuery dataset.

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

    def execute_query(self, query: str) -> list:
        """
        Executes a SQL query on BigQuery and returns the results.

        Args:
            query (str): The SQL query string to execute.

        Returns:
            list: A list of BigQuery Row objects, or an empty list if an error occurs.
        """
        logger.info("Executing BigQuery query...")
        try:
            query_job = self.client.query(query)  # API request
            results = query_job.result()  # Waits for job to complete
            rows = [
                dict(row) for row in results
            ]  # Convert rows to dictionaries for easier handling
            logger.info(f"Query executed successfully. Fetched {len(rows)} rows.")
            return rows
        except GoogleCloudError as e:
            logger.error(f"BigQuery query failed with Google Cloud Error: {e}")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred during query execution: {e}")
            return []
