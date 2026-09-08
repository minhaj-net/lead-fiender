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
  Contact detection
      ↓
  Duplicate check
      ↓
  Lead scoring
      ↓
  Lead model (ready for DB insert)

This module does NOT handle browser automation (see automation.py).
It receives a raw data dict extracted by the Playwright layer and
returns a fully processed Lead dataclass.
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
            - country:        str | None
            - city:           str | None
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
        country       = raw.get("country"),
        city          = raw.get("city"),
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
        contacts = detect_contacts(
            phone_field    = raw.get("phone_field"),
            whatsapp_field = raw.get("whatsapp_field"),
            about_text     = about_text,
            post_text      = post_text,
        )
        lead.business_phone    = contacts.get("business_phone")
        lead.business_whatsapp = contacts.get("business_whatsapp")

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
            "is_business":       biz_result["is_business"],
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

        lead.status = "QUALIFIED"
        logger.info(
            "Qualified lead: %s | score=%d | priority=%s",
            business_name, lead.lead_score, lead.lead_priority,
        )
        return lead, "QUALIFIED"

    except Exception as exc:
        logger.error("Pipeline error for '%s': %s", business_name, exc, exc_info=True)
        lead.status = "FAILED"
        return lead, "FAILED"
