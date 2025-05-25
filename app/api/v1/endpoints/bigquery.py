# app/api/v1/endpoints/bigquery.py
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.dependencies import get_bigquery_reader
from app.services.bigquery_service import BigQueryReader
from app.api.models.bigquery_models import QueryRequest, TableListResponse, QueryResponse, QueryResultRow

router = APIRouter()

@router.get("/list_tables", response_model=TableListResponse, summary="List tables in a public BigQuery dataset")
async def list_bigquery_tables(
    dataset_project: str = "bigquery-public-data",
    dataset_id: str = "thelook_ecommerce",
    max_results: int = 10,
    bq_reader: BigQueryReader = Depends(get_bigquery_reader)
):
    """
    Lists tables available in a specified BigQuery public dataset.
    """
    tables = bq_reader.list_tables_in_dataset(dataset_project, dataset_id, max_results)
    if tables is None: # Indicates an error occurred in the service layer
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tables from BigQuery. Check logs for details."
        )
    elif not tables: # Indicates dataset not found or empty
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_project}.{dataset_id}' not found or contains no tables."
        )
    return TableListResponse(project=dataset_project, dataset_id=dataset_id, tables=tables)

@router.post("/query", response_model=QueryResponse, summary="Execute a custom SQL query on BigQuery")
async def execute_bigquery_query(
    request: QueryRequest,
    bq_reader: BigQueryReader = Depends(get_bigquery_reader)
):
    """
    Executes a SQL query on BigQuery.
    """
    rows = bq_reader.execute_query(request.query)
    if rows is None: # Indicates an error occurred
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute BigQuery query. Check logs for details."
        )
    
    # Convert list of dicts to list of QueryResultRow models
    formatted_rows = [QueryResultRow(data=row) for row in rows]

    return QueryResponse(rows=formatted_rows, row_count=len(formatted_rows))