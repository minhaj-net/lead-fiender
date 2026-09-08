"""
backend/services/csv_exporter.py
──────────────────────────────────
Exports qualified leads from MySQL to a timestamped CSV file using Pandas.

Output columns (matches TODO spec):
  Business Name, Category, Facebook URL, Page URL, Country, City,
  Website, Website Status, Business Phone, Business WhatsApp,
  Source, Source Post, Lead Score, Priority, Status

Output file: data/Codeloom_Leads_YYYY-MM-DD.csv
"""
from __future__ import annotations

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
    "source":            "Source",
    "source_post":       "Source Post",
    "lead_score":        "Lead Score",
    "lead_priority":     "Priority",
    "status":            "Status",
    "created_at":        "Created At",
}


def export_leads_to_csv(
    status_filter: str = "QUALIFIED",
    priority_filter: list[str] | None = None,
    output_dir: str | None = None,
) -> dict:
    """
    Export leads to a CSV file.

    Args:
        status_filter:    Only export leads with this status (default: QUALIFIED).
        priority_filter:  Optional list of priorities to include, e.g. ['HOT', 'GOOD'].
        output_dir:       Override output directory (default: settings.csv_export_dir).

    Returns:
        {"file_path": str, "lead_count": int, "exported_at": datetime}
    """
    output_dir = output_dir or settings.csv_export_dir
    os.makedirs(output_dir, exist_ok=True)

    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # Build query
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
        rows = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    if not rows:
        logger.warning("No leads found matching export criteria.")
        rows = []

    df = pd.DataFrame(rows, columns=list(_COLUMNS.keys()))

    # Rename columns to display names
    df.rename(columns=_COLUMNS, inplace=True)

    # Format datetime column
    if "Created At" in df.columns:
        df["Created At"] = pd.to_datetime(df["Created At"]).dt.strftime("%Y-%m-%d %H:%M:%S")

    # Build filename
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
