"""
backend/routers/leads.py
─────────────────────────
Lead management endpoints:

  GET    /leads            — list leads (filterable)
  GET    /leads/export     — export to CSV
  GET    /leads/{id}       — get single lead
  DELETE /leads/{id}       — delete a lead
  PATCH  /leads/{id}       — update lead fields
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.database import get_connection
from backend.schemas import LeadRead, LeadUpdate, ExportResponse
from backend.services.csv_exporter import export_leads_to_csv
from backend.utils.logger import get_logger

router = APIRouter(prefix="/leads", tags=["leads"])
logger = get_logger(__name__)


def _row_to_lead_read(row: dict) -> LeadRead:
    return LeadRead(**row)


@router.get("", response_model=list[LeadRead], summary="List qualified leads")
def list_leads(
    status:   str | None = Query(None, description="Filter by status"),
    priority: str | None = Query(None, description="Filter by priority (HOT/GOOD/MEDIUM/LOW)"),
    limit:    int = Query(100, ge=1, le=1000),
    offset:   int = Query(0, ge=0),
) -> list[LeadRead]:
    """
    Return a paginated list of leads.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        wheres: list[str] = []
        params: list      = []

        if status:
            wheres.append("status = %s")
            params.append(status.upper())
        if priority:
            wheres.append("lead_priority = %s")
            params.append(priority.upper())

        where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ""
        cursor.execute(
            f"SELECT * FROM leads {where_sql} ORDER BY lead_score DESC, created_at DESC "
            f"LIMIT %s OFFSET %s",
            (*params, limit, offset),
        )
        rows = cursor.fetchall()
        return [_row_to_lead_read(r) for r in rows]
    finally:
        cursor.close()
        conn.close()


@router.get("/export", response_model=ExportResponse, summary="Export leads to CSV")
def export_leads(
    status:   str = Query("QUALIFIED"),
    priority: str | None = Query(None, description="Comma-separated priorities, e.g. HOT,GOOD"),
) -> ExportResponse:
    """
    Export leads to a dated CSV file in the data/ directory.
    """
    priority_list = [p.strip().upper() for p in priority.split(",")] if priority else None
    try:
        result = export_leads_to_csv(
            status_filter   = status.upper(),
            priority_filter = priority_list,
        )
        return ExportResponse(
            file_path   = result["file_path"],
            lead_count  = result["lead_count"],
            exported_at = result["exported_at"],
        )
    except Exception as exc:
        logger.error("CSV export failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{lead_id}", response_model=LeadRead, summary="Get a single lead")
def get_lead(lead_id: int) -> LeadRead:
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found.")
        return _row_to_lead_read(row)
    finally:
        cursor.close()
        conn.close()


@router.patch("/{lead_id}", response_model=LeadRead, summary="Update lead fields")
def update_lead(lead_id: int, update: LeadUpdate) -> LeadRead:
    data = update.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        set_clause = ", ".join(f"{k} = %s" for k in data)
        cursor.execute(
            f"UPDATE leads SET {set_clause} WHERE id = %s",
            (*data.values(), lead_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found.")
        cursor.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
        return _row_to_lead_read(cursor.fetchone())
    finally:
        cursor.close()
        conn.close()


@router.delete("/{lead_id}", summary="Delete a lead")
def delete_lead(lead_id: int) -> dict:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leads WHERE id = %s", (lead_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found.")
        return {"message": f"Lead {lead_id} deleted."}
    finally:
        cursor.close()
        conn.close()
