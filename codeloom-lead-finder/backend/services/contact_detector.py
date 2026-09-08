"""
backend/services/contact_detector.py
──────────────────────────────────────
Extracts publicly provided business contact information from
publicly available Facebook business page content.

IMPORTANT:
- Only processes information publicly provided as business contact info.
- Does NOT attempt to access private, hidden, or restricted information.
- Does NOT collect personal phone numbers.
"""
from __future__ import annotations

import re

from backend.utils.logger import get_logger
from backend.utils.normalizers import normalize_phone, is_valid_phone

logger = get_logger(__name__)

# ── Phone number patterns ─────────────────────────────────────────────────────
# BD numbers start with +880 or 01, 11 digits total
# Generic international: +CC XXXXXXXXXX

_PHONE_PATTERNS = [
    # International format: +880 1711-123456, +880-171-123-4567
    re.compile(r"\+\d{1,3}[\s\-\.]?\d{2,4}[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}"),
    # BD local: 01XXXXXXXXX (11 digits)
    re.compile(r"\b01[3-9]\d{8}\b"),
    # Parenthesized area codes: (880) 1711 123456
    re.compile(r"\(\d{2,4}\)\s*\d{3,4}[\s\-\.]?\d{4,7}"),
]

# ── WhatsApp detection patterns ───────────────────────────────────────────────

_WHATSAPP_PATTERNS = [
    # Explicit WhatsApp link
    re.compile(r"(?:wa\.me|api\.whatsapp\.com/send)[/?](?:phone=)?(\+?[\d\s\-\.]{7,15})", re.IGNORECASE),
    # "WhatsApp: 01711..." or "WhatsApp/Viber: +880..."
    re.compile(r"whatsapp[\s:/]+(\+?[\d\s\-\.]{7,15})", re.IGNORECASE),
]

# ── Email pattern ─────────────────────────────────────────────────────────────

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)


def _extract_phones(text: str) -> list[str]:
    """Extract and normalize all phone numbers found in text."""
    found: list[str] = []
    for pattern in _PHONE_PATTERNS:
        for match in pattern.findall(text):
            normalized = normalize_phone(match)
            if normalized and is_valid_phone(normalized) and normalized not in found:
                found.append(normalized)
    return found


def _extract_whatsapp(text: str) -> str | None:
    """
    Extract a WhatsApp business contact number.
    Prefers explicit wa.me links, then 'WhatsApp: XXXX' text patterns.
    Returns normalized number or None.
    """
    for pattern in _WHATSAPP_PATTERNS:
        match = pattern.search(text)
        if match:
            raw = match.group(1) if match.lastindex else match.group(0)
            normalized = normalize_phone(raw)
            if normalized and is_valid_phone(normalized):
                return normalized
    return None


def _extract_email(text: str) -> str | None:
    """Extract the first business email address found in text."""
    match = _EMAIL_PATTERN.search(text)
    return match.group(0).lower() if match else None


def detect_contacts(
    phone_field: str | None = None,
    whatsapp_field: str | None = None,
    about_text: str | None = None,
    post_text: str | None = None,
) -> dict:
    """
    Extract publicly provided business contact information.

    Args:
        phone_field:     Explicit phone field from FB page (if available).
        whatsapp_field:  Explicit WhatsApp field from FB page (if available).
        about_text:      'About' section text.
        post_text:       Business post text.

    Returns:
        {
            "business_phone":    str | None,
            "business_whatsapp": str | None,
            "business_email":    str | None,
            "phone_source":      str,
            "whatsapp_source":   str,
        }
    """
    result = {
        "business_phone":    None,
        "business_whatsapp": None,
        "business_email":    None,
        "phone_source":      "none",
        "whatsapp_source":   "none",
    }

    # ── Phone ──────────────────────────────────────────────────────────────────
    if phone_field and phone_field.strip():
        normalized = normalize_phone(phone_field.strip())
        if normalized and is_valid_phone(normalized):
            result["business_phone"] = normalized
            result["phone_source"]   = "phone_field"
            logger.debug("Phone from explicit field: %s", normalized)

    if not result["business_phone"]:
        combined_text = " ".join(filter(None, [about_text, post_text]))
        phones = _extract_phones(combined_text)
        if phones:
            result["business_phone"] = phones[0]
            result["phone_source"]   = "text_scan"
            logger.debug("Phone from text scan: %s", phones[0])

    # ── WhatsApp ───────────────────────────────────────────────────────────────
    if whatsapp_field and whatsapp_field.strip():
        normalized = normalize_phone(whatsapp_field.strip())
        if normalized and is_valid_phone(normalized):
            result["business_whatsapp"] = normalized
            result["whatsapp_source"]   = "whatsapp_field"
            logger.debug("WhatsApp from explicit field: %s", normalized)

    if not result["business_whatsapp"]:
        combined_text = " ".join(filter(None, [about_text, post_text]))
        wa = _extract_whatsapp(combined_text)
        if wa:
            result["business_whatsapp"] = wa
            result["whatsapp_source"]   = "text_scan"
            logger.debug("WhatsApp from text scan: %s", wa)

    # ── Email ──────────────────────────────────────────────────────────────────
    combined_text = " ".join(filter(None, [about_text, post_text]))
    email = _extract_email(combined_text)
    if email:
        result["business_email"] = email
        logger.debug("Email found: %s", email)

    return result
