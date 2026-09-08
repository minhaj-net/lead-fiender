"""
backend/services/duplicate_checker.py
───────────────────────────────────────
Checks whether a lead candidate already exists in the database before insert.

Duplicate key strategy (checked in order):
  1. Normalized Facebook URL — most reliable stable identifier
  2. Normalized phone + normalized business name combo — secondary fallback

Returns (is_duplicate: bool, existing_id: int | None).
"""
from __future__ import annotations

from backend.database import get_connection
from backend.utils.logger import get_logger
from backend.utils.normalizers import normalize_facebook_url, normalize_phone, normalize_business_name

logger = get_logger(__name__)


def is_duplicate(
    facebook_url: str | None = None,
    business_phone: str | None = None,
    business_name: str | None = None,
) -> tuple[bool, int | None]:
    """
    Check if a lead already exists in the database.

    Returns:
        (True, existing_id)   if a duplicate is found
        (False, None)         if no duplicate
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Check by normalized Facebook URL
        if facebook_url:
            norm_url = normalize_facebook_url(facebook_url)
            if norm_url:
                cursor.execute(
                    "SELECT id FROM leads WHERE facebook_url = %s LIMIT 1",
                    (norm_url,),
                )
                row = cursor.fetchone()
                if row:
                    logger.info("Duplicate found by FB URL: %s (id=%s)", norm_url, row["id"])
                    return True, row["id"]

        # 2. Check by phone + normalized business name
        if business_phone and business_name:
            norm_phone = normalize_phone(business_phone)
            norm_name  = normalize_business_name(business_name)
            if norm_phone and norm_name:
                cursor.execute(
                    """
                    SELECT id FROM leads
                    WHERE business_phone = %s
                      AND LOWER(TRIM(business_name)) = %s
                    LIMIT 1
                    """,
                    (norm_phone, norm_name),
                )
                row = cursor.fetchone()
                if row:
                    logger.info(
                        "Duplicate found by phone+name: %s / %s (id=%s)",
                        norm_phone, norm_name, row["id"],
                    )
                    return True, row["id"]

        return False, None

    except Exception as exc:
        logger.error("duplicate_checker error: %s", exc)
        return False, None  # Fail open — don't block processing on DB error
    finally:
        cursor.close()
        conn.close()
