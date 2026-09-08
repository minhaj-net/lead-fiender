"""
backend/routers/health.py
──────────────────────────
GET /health — backend liveness check used by the Chrome extension
to verify the backend is running before enabling START/STOP.
"""
from fastapi import APIRouter
from mysql.connector import Error as MySQLError

from backend.database import get_connection
from backend.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Backend health check")
def health_check() -> HealthResponse:
    """
    Returns:
      - status: "ok"
      - database: "connected" | "error"
      - version: API version string
    """
    db_status = "unknown"
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        db_status = "connected"
    except MySQLError:
        db_status = "error"

    return HealthResponse(status="ok", database=db_status, version="1.0.0")
