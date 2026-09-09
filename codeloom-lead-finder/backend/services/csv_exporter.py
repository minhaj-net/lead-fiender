"""
backend/services/csv_exporter.py
──────────────────────────────────
Exports qualified leads from MySQL.

Two modes:
  export_leads_to_csv()  — writes a dated CSV file to disk (legacy / server-side)
  build_csv_bytes()      — returns raw UTF-8-BOM CSV bytes for streaming download

Output columns:
  Business Name, Category, Facebook URL, Page URL, Country, City,
  Website, Website Status, Business Phone, Business WhatsApp, Business Email,
  Source, Source Post, Lead Score, Priority, Status, Created At

Output file (disk mode): data/Codeloom_Leads_YYYY-MM-DD.csv
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import pandas as pd

from backend.config import settings
from backend.database import get_connection
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# CSV column display names (order matters)
_COLUMNS = {
    "business_name":     "Business Name",
    "category":          "Category",
    "facebook_url":      "Facebook URL",
    "page_url":          "Page URL",
    "country":           "Country",
    "city":              "City",
    "website":           "Website",
    "website_status":    "Website Status",
    "business_phone":    "Business Phone",
    "business_whatsapp": "Business WhatsApp",
    "business_email":    "Business Email",
    "source":            "Source",
    "source_post":       "Source Post",
    "lead_score":        "Lead Score",
    "lead_priority":     "Priority",
    "status":            "Status",
    "created_at":        "Created At",
}


def _fetch_leads(
    status_filter: str = "QUALIFIED",
    priority_filter: list[str] | None = None,
) -> list[dict]:
    """Fetch leads from MySQL matching the given filters."""
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        where_clauses = ["status = %s"]
        params: list = [status_filter]

        if priority_filter:
            placeholders = ",".join(["%s"] * len(priority_filter))
            where_clauses.append(f"lead_priority IN ({placeholders})")
            params.extend(priority_filter)

        where_sql = " AND ".join(where_clauses)
        query = f"""
            SELECT {', '.join(_COLUMNS.keys())}
            FROM leads
            WHERE {where_sql}
            ORDER BY lead_score DESC, created_at DESC
        """
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def _rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Convert DB rows to a renamed, formatted DataFrame."""
    df = pd.DataFrame(rows if rows else [], columns=list(_COLUMNS.keys()))
    df.rename(columns=_COLUMNS, inplace=True)
    if "Created At" in df.columns and len(df) > 0:
        df["Created At"] = pd.to_datetime(df["Created At"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def build_csv_bytes(
    status_filter: str = "QUALIFIED",
    priority_filter: list[str] | None = None,
) -> bytes:
    """
    Build CSV content in memory and return as UTF-8-BOM encoded bytes.
    Used by the /leads/download streaming endpoint.

    UTF-8-BOM ensures Excel opens the file correctly without encoding issues.
    """
    rows = _fetch_leads(status_filter, priority_filter)
    if not rows:
        logger.warning("No leads found for CSV download.")
    df   = _rows_to_dataframe(rows)
    buf  = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    # Prepend UTF-8 BOM so Excel auto-detects encoding
    return "\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8")


def export_leads_to_csv(
    status_filter: str = "QUALIFIED",
    priority_filter: list[str] | None = None,
    output_dir: str | None = None,
) -> dict:
    """
    Export leads to a CSV file on disk.

    Args:
        status_filter:    Only export leads with this status (default: QUALIFIED).
        priority_filter:  Optional list of priorities to include, e.g. ['HOT', 'GOOD'].
        output_dir:       Override output directory (default: settings.csv_export_dir).

    Returns:
        {"file_path": str, "lead_count": int, "exported_at": datetime}
    """
    output_dir = output_dir or settings.csv_export_dir
    os.makedirs(output_dir, exist_ok=True)

    rows = _fetch_leads(status_filter, priority_filter)
    if not rows:
        logger.warning("No leads found matching export criteria.")

    df = _rows_to_dataframe(rows)

    date_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename  = f"Codeloom_Leads_{date_str}.csv"
    file_path = os.path.join(output_dir, filename)

    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    logger.info("Exported %d leads to %s", len(rows), file_path)

    return {
        "file_path":   file_path,
        "lead_count":  len(rows),
        "exported_at": datetime.now(timezone.utc),
    }
