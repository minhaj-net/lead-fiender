"""
backend/services/website_detector.py
──────────────────────────────────────
Detects whether a business has an external website based on
publicly available Facebook page information.

Result codes:
  YES       — a clear external website URL was found
  NO        — no website found in the checked public information
              (does NOT mean they have no website anywhere on the internet)
  UNCERTAIN — ambiguous; may need AI or manual review

Only processes publicly provided information — no private data access.
"""
from __future__ import annotations

import re

from backend.services import ai_service
from backend.utils.logger import get_logger
from backend.utils.normalizers import normalize_url

logger = get_logger(__name__)

# ── Patterns ───────────────────────────────────────────────────────────────────

# Match URLs that look like real external websites
_URL_PATTERN = re.compile(
    r"https?://(?!(?:www\.)?facebook\.com|fb\.com|fb\.watch|m\.facebook\.com)"
    r"[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
    re.IGNORECASE,
)

# Domains that are NOT standalone websites (social/messaging platforms)
_SOCIAL_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "youtube.com", "linkedin.com", "snapchat.com",
    "wa.me", "api.whatsapp.com", "t.me", "telegram.org",
    "messenger.com", "m.me",
}


def _is_social_url(url: str) -> bool:
    """Return True if the URL points to a known social/messaging platform."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _SOCIAL_DOMAINS)


def _extract_external_urls(text: str) -> list[str]:
    """Find all external (non-Facebook) URLs in a text string."""
    matches = _URL_PATTERN.findall(text)
    return [u for u in matches if not _is_social_url(u)]


# ── What counts as YES / NO / UNCERTAIN ──────────────────────────────────────
# YES:       A clear external website URL is present in the public info checked.
# NO:        No website URL found after checking all available public fields.
# UNCERTAIN: A URL-like string was found but it's ambiguous, malformed, or
#            the pattern could not determine its nature with confidence.

def detect_website(
    facebook_page_url: str | None = None,
    website_field: str | None = None,
    about_text: str | None = None,
    post_text: str | None = None,
    use_ai_for_uncertain: bool = True,
) -> dict:
    """
    Detect whether a business has an external website.

    Args:
        facebook_page_url:  The Facebook page URL (excluded from detection).
        website_field:      The explicit 'Website' field from the FB page, if any.
        about_text:         The 'About' section text from the FB page.
        post_text:          Text from a relevant business post.
        use_ai_for_uncertain: Whether to call AI for UNCERTAIN cases.

    Returns:
        {
            "status":  "YES" | "NO" | "UNCERTAIN",
            "url":     str | None,   # normalized URL if found
            "method":  str,          # where it was found
            "note":    str,
        }
    """

    # 1. Check explicit website field first (highest confidence)
    if website_field and website_field.strip():
        candidate = website_field.strip()
        if not _is_social_url(candidate):
            normalized = normalize_url(candidate)
            logger.debug("Website found in explicit field: %s", normalized)
            return {
                "status": "YES",
                "url":    normalized,
                "method": "website_field",
                "note":   "Found in explicit Facebook website field.",
            }

    # 2. Scan about text
    if about_text:
        found = _extract_external_urls(about_text)
        if found:
            normalized = normalize_url(found[0])
            logger.debug("Website found in about text: %s", normalized)
            return {
                "status": "YES",
                "url":    normalized,
                "method": "about_text",
                "note":   "Found in Facebook About section.",
            }

    # 3. Scan post text
    if post_text:
        found = _extract_external_urls(post_text)
        if found:
            normalized = normalize_url(found[0])
            logger.debug("Website found in post text: %s", normalized)
            return {
                "status": "YES",
                "url":    normalized,
                "method": "post_text",
                "note":   "Found in business post.",
            }

    # 4. Look for domain-like patterns that might be websites without http://
    _NAKED_DOMAIN = re.compile(
        r"\b(?!www\.facebook\.com|fb\.com)www\.[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}\b"
    )
    combined_text = " ".join(filter(None, [about_text, post_text]))
    naked = _NAKED_DOMAIN.findall(combined_text)
    if naked:
        if use_ai_for_uncertain:
            logger.info("Naked domain found (%s) — sending to AI for resolution.", naked[0])
            ai_result = ai_service.resolve_website_ambiguity(combined_text[:800])
            if ai_result.get("has_website"):
                return {
                    "status": "YES",
                    "url":    normalize_url(ai_result.get("found_url") or naked[0]),
                    "method": "ai_resolved",
                    "note":   "Confirmed by AI from ambiguous domain pattern.",
                }
        return {
            "status": "UNCERTAIN",
            "url":    None,
            "method": "pattern_match",
            "note":   f"Possible domain '{naked[0]}' found but could not confirm.",
        }

    # 5. No website found in any checked public information
    logger.debug("No website found in public information.")
    return {
        "status": "NO",
        "url":    None,
        "method": "exhausted",
        "note":   (
            "No website URL found in the checked public Facebook information. "
            "This does not guarantee the business has no website."
        ),
    }
