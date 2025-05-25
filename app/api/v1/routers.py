# app/api/v1/routers.py
from fastapi import APIRouter
from app.api.v1.endpoints import bigquery

api_router = APIRouter()
api_router.include_router(bigquery.router, prefix="/bigquery", tags=["BigQuery"])