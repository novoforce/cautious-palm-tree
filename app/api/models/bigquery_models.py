# app/api/models/bigquery_models.py
from pydantic import BaseModel, Field, ValidationError
from typing import List, Dict, Any, Optional

class QueryRequest(BaseModel):
    query: str = Field(..., example="SELECT * FROM `bigquery-public-data.thelook_ecommerce.orders` LIMIT 10")

class TableListResponse(BaseModel):
    project: str
    dataset_id: str
    tables: List[str]

class QueryResultRow(BaseModel):
    # This model is flexible for varying BigQuery row structures
    # You might want to define more specific models for specific queries
    data: Dict[str, Any]

class QueryResponse(BaseModel):
    rows: List[QueryResultRow]
    row_count: int