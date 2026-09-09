"""
backend/services/lead_discovery.py
────────────────────────────────────
Coordinates the full lead-discovery pipeline for a single page/profile:

  Raw page data
      ↓
  Business identification
      ↓
  Website detection
      ↓
  Contact detection  (phone, whatsapp, email)
      ↓
  Duplicate check
      ↓
  Lead scoring
      ↓
  Field completeness  (fill "Not publicly listed" for missing fields)
      ↓
  Lead model (ready for DB insert)

This module does NOT handle browser automation (see automation.py).
It receives a raw data dict extracted by the Playwright layer and
returns a fully processed Lead dataclass.

Field completeness policy
─────────────────────────
Every lead that reaches QUALIFIED status must have every human-readable
field set to either a real extracted value or a meaningful fallback string.
We never store None / null for display fields — that makes CSV/UI look empty.

Fallback values used:
  "Not publicly listed"  — field exists on FB but wasn't public / accessible
  "Not found"            — field was not present anywhere in the checked data
"""
from __future__ import annotations

from backend.models import Lead
from backend.services.business_identifier import identify_business
from backend.services.website_detector import detect_website
from backend.services.contact_detector import detect_contacts
from backend.services.duplicate_checker import is_duplicate
from backend.services.lead_scorer import score_lead
from backend.utils.logger import get_logger
from backend.utils.normalizers import normalize_facebook_url, normalize_url

logger = get_logger(__name__)

# ── Fallback sentinel values ──────────────────────────────────────────────────
# These are stored as strings in the DB, not NULL, so CSVs always have content.

_NOT_LISTED = "Not publicly listed"
_NOT_FOUND  = "Not found"


def _apply_field_fallbacks(lead: Lead) -> None:
    """
    Replace None values on a lead's display fields with meaningful fallback
    strings.  Only applied to QUALIFIED leads before saving.

    Rules:
    - country / city: use "Not publicly listed" — these should be on the page
      but Facebook often hides them unless the business filled the field.
    - business_phone / business_whatsapp: use "Not publicly listed" — contact
      info is often present but may not be public.
    - business_email: use "Not publicly listed" — email fields are rarely
      publicly shown on FB pages.
    - website: only set when website_status == "NO" so it's clearly absent.
    - business_name / category: use "Not found" if somehow missing.
    """
    if not lead.business_name or not lead.business_name.strip():
        lead.business_name = _NOT_FOUND

    if not lead.category or not lead.category.strip():
        lead.category = _NOT_FOUND

    if not lead.country or not lead.country.strip():
        lead.country = _NOT_LISTED

    if not lead.city or not lead.city.strip():
        lead.city = _NOT_LISTED

    if not lead.business_phone or not lead.business_phone.strip():
        lead.business_phone = _NOT_LISTED

    if not lead.business_whatsapp or not lead.business_whatsapp.strip():
        lead.business_whatsapp = _NOT_LISTED

    if not lead.business_email or not lead.business_email.strip():
        lead.business_email = _NOT_LISTED

    # website: only fill fallback when we know there's no website
    if lead.website_status == "NO" and (not lead.website or not lead.website.strip()):
        lead.website = _NOT_FOUND


def process_candidate(raw: dict) -> tuple[Lead, str]:
    """
    Process a raw page/profile data dict through the full pipeline.

    Args:
        raw: dict with keys:
            - facebook_url:   str — Facebook page/profile URL
            - page_url:       str — canonical page URL (may differ)
            - business_name:  str
            - category_hint:  str | None — category from FB page
            - about_text:     str | None
            - post_text:      str | None
            - website_field:  str | None — explicit website from FB
            - phone_field:    str | None — explicit phone from FB
            - whatsapp_field: str | None — explicit WhatsApp from FB
            - email_field:    str | None — explicit email from FB page
            - country:        str | None — extracted from page content
            - city:           str | None — extracted from page content
            - source:         str | None — name of source group/page
            - source_post:    str | None — snippet of the source post

    Returns:
        (Lead, status_code)

    Status codes:
        QUALIFIED   — lead passed all checks, ready to insert
        SKIPPED     — not a business, website found, or below quality threshold
        DUPLICATE   — already in database
        UNCERTAIN   — could not determine business/website with confidence
        FAILED      — an unexpected error occurred
    """
    facebook_url  = normalize_facebook_url(raw.get("facebook_url"))
    business_name = (raw.get("business_name") or "").strip() or None

    lead = Lead(
        facebook_url  = facebook_url,
        page_url      = normalize_url(raw.get("page_url")),
        business_name = business_name,
        country       = raw.get("country"),    # may be None; fallback applied later
        city          = raw.get("city"),        # may be None; fallback applied later
        source        = raw.get("source"),
        source_post   = (raw.get("source_post") or "")[:500] or None,
    )

    try:
        # ── Step 1: Business identification ──────────────────────────────────
        about_text = raw.get("about_text") or ""
        post_text  = raw.get("post_text") or ""
        combined   = f"{about_text} {post_text}".strip()

        biz_result = identify_business(
            public_text   = combined,
            category_hint = raw.get("category_hint"),
        )

        if not biz_result["is_business"]:
            lead.status = "SKIPPED"
            logger.info("Skipped (not a business): %s", business_name)
            return lead, "SKIPPED"

        lead.category = biz_result["category"]

        # ── Step 2: Website detection ─────────────────────────────────────────
        website_result = detect_website(
            facebook_page_url = facebook_url,
            website_field     = raw.get("website_field"),
            about_text        = about_text,
            post_text         = post_text,
        )

        lead.website_status = website_result["status"]
        lead.website        = website_result.get("url")

        if website_result["status"] == "YES":
            lead.status = "SKIPPED"
            logger.info("Skipped (has website): %s → %s", business_name, lead.website)
            return lead, "SKIPPED"

        # ── Step 3: Contact detection ─────────────────────────────────────────
        # Pass email_field from raw data so contact_detector can use it
        contacts = detect_contacts(
            phone_field    = raw.get("phone_field"),
            whatsapp_field = raw.get("whatsapp_field"),
            email_field    = raw.get("email_field"),
            about_text     = about_text,
            post_text      = post_text,
        )
        lead.business_phone    = contacts.get("business_phone")
        lead.business_whatsapp = contacts.get("business_whatsapp")
        lead.business_email    = contacts.get("business_email")

        # ── Step 4: Duplicate check ───────────────────────────────────────────
        dup, dup_id = is_duplicate(
            facebook_url   = facebook_url,
            business_phone = lead.business_phone,
            business_name  = business_name,
        )
        if dup:
            lead.status = "DUPLICATE"
            logger.info("Duplicate (existing id=%s): %s", dup_id, business_name)
            return lead, "DUPLICATE"

        # ── Step 5: Lead scoring ──────────────────────────────────────────────
        score_input = {
            **lead.to_dict(),
            "is_business":         biz_result["is_business"],
            "business_confidence": biz_result["confidence"],
        }
        score_result = score_lead(score_input)
        lead.lead_score    = score_result["score"]
        lead.lead_priority = score_result["priority"]

        # ── Step 6: Minimum quality gate ──────────────────────────────────────
        if lead.lead_score < 30:
            lead.status = "SKIPPED"
            logger.info("Skipped (low score %d): %s", lead.lead_score, business_name)
            return lead, "SKIPPED"

        if website_result["status"] == "UNCERTAIN":
            lead.status = "UNCERTAIN"
            logger.info("Uncertain website: %s", business_name)
            return lead, "UNCERTAIN"

        # ── Step 7: Field completeness — fill fallback values ─────────────────
        _apply_field_fallbacks(lead)

        lead.status = "QUALIFIED"
        logger.info(
            "Qualified lead: %s | score=%d | priority=%s | country=%s | city=%s | email=%s",
            business_name, lead.lead_score, lead.lead_priority,
            lead.country, lead.city, lead.business_email,
        )
        return lead, "QUALIFIED"

    except Exception as exc:
        logger.error("Pipeline error for '%s': %s", business_name, exc, exc_info=True)
        lead.status = "FAILED"
        return lead, "FAILED"
