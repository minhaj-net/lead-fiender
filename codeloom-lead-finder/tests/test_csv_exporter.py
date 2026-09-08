"""
tests/test_csv_exporter.py
───────────────────────────
Unit tests for the CSV exporter service.
Uses a temporary directory and mocks the DB connection.
Run with: pytest tests/test_csv_exporter.py -v
"""
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from backend.services.csv_exporter import export_leads_to_csv, _COLUMNS


# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_ROWS = [
    {
        "business_name":     "Mama's Kitchen",
        "category":          "Restaurant",
        "facebook_url":      "https://www.facebook.com/mamaskitchen",
        "page_url":          "https://www.facebook.com/mamaskitchen",
        "country":           "Bangladesh",
        "city":              "Dhaka",
        "website":           None,
        "website_status":    "NO",
        "business_phone":    "+8801711123456",
        "business_whatsapp": "+8801711123456",
        "source":            "bd_business_group",
        "source_post":       "Delicious food, order now!",
        "lead_score":        88,
        "lead_priority":     "GOOD",
        "status":            "QUALIFIED",
        "created_at":        datetime(2026, 9, 6, 12, 0, 0),
    },
    {
        "business_name":     "Fashion Hub",
        "category":          "Clothing & Fashion",
        "facebook_url":      "https://www.facebook.com/fashionhub",
        "page_url":          "https://www.facebook.com/fashionhub",
        "country":           "Bangladesh",
        "city":              "Chittagong",
        "website":           None,
        "website_status":    "NO",
        "business_phone":    "+8801812345678",
        "business_whatsapp": None,
        "source":            "bd_business_group",
        "source_post":       "New collection in stock!",
        "lead_score":        72,
        "lead_priority":     "GOOD",
        "status":            "QUALIFIED",
        "created_at":        datetime(2026, 9, 6, 13, 0, 0),
    },
]


def _mock_get_connection(rows):
    """Return a mock DB connection that yields given rows."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn


class TestCsvExporter:

    def test_export_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.services.csv_exporter.get_connection") as mock_gc:
                mock_gc.return_value = _mock_get_connection(SAMPLE_ROWS)
                result = export_leads_to_csv(output_dir=tmpdir)

            assert os.path.exists(result["file_path"])
            assert result["file_path"].endswith(".csv")

    def test_export_correct_row_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.services.csv_exporter.get_connection") as mock_gc:
                mock_gc.return_value = _mock_get_connection(SAMPLE_ROWS)
                result = export_leads_to_csv(output_dir=tmpdir)

            assert result["lead_count"] == len(SAMPLE_ROWS)

    def test_export_columns_match_spec(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.services.csv_exporter.get_connection") as mock_gc:
                mock_gc.return_value = _mock_get_connection(SAMPLE_ROWS)
                result = export_leads_to_csv(output_dir=tmpdir)

            df = pd.read_csv(result["file_path"], encoding="utf-8-sig")
            expected_cols = set(_COLUMNS.values())
            actual_cols   = set(df.columns)
            assert expected_cols == actual_cols

    def test_export_empty_leads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.services.csv_exporter.get_connection") as mock_gc:
                mock_gc.return_value = _mock_get_connection([])
                result = export_leads_to_csv(output_dir=tmpdir)

            assert result["lead_count"] == 0
            assert os.path.exists(result["file_path"])

    def test_filename_contains_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.services.csv_exporter.get_connection") as mock_gc:
                mock_gc.return_value = _mock_get_connection(SAMPLE_ROWS)
                result = export_leads_to_csv(output_dir=tmpdir)

            filename = os.path.basename(result["file_path"])
            assert filename.startswith("Codeloom_Leads_")
            assert filename.endswith(".csv")

    def test_exported_at_is_datetime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.services.csv_exporter.get_connection") as mock_gc:
                mock_gc.return_value = _mock_get_connection(SAMPLE_ROWS)
                result = export_leads_to_csv(output_dir=tmpdir)

            assert isinstance(result["exported_at"], datetime)
