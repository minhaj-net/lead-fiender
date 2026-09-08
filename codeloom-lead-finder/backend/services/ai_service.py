"""
backend/services/ai_service.py
───────────────────────────────
OpenAI API wrapper for:
  1. Business classification (is_business, category, confidence)
  2. Lead scoring (score, priority, reason)
  3. Ambiguous case resolution (website / contact ambiguity)

Security:
  - API key is read from settings (loaded from .env).
  - Only public business text is sent — no personal information.
  - Usage is logged so you can monitor costs.
"""
from __future__ import annotations

import json

from openai import OpenAI, OpenAIError

from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Lazy-initialized client so the module can be imported without a valid key
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _chat(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> dict | None:
    """
    Internal helper: call the chat completion API and parse JSON response.
    Returns parsed dict or None on failure.
    """
    try:
        response = _get_client().chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        logger.debug("AI raw response: %s", raw)
        return json.loads(raw)
    except OpenAIError as exc:
        logger.error("OpenAI API error: %s", exc)
        return None
    except json.JSONDecodeError as exc:
        logger.error("AI response was not valid JSON: %s", exc)
        return None


# ── Business classification ────────────────────────────────────────────────────

BUSINESS_CLASSIFIER_SYSTEM = """
You are a business classification assistant for a web-development agency.
You receive a short text from a public Facebook page or post and decide:
- Whether it represents a business offering products or services
- The most likely business category
- Your confidence level (0.0 to 1.0)

Return ONLY valid JSON in this exact format:
{"is_business": true/false, "category": "string", "confidence": 0.0}

Category examples: Restaurant, Retail Shop, Clothing, Electronics, Beauty Salon,
Construction, Transport, Education, Healthcare, Food & Beverage, Other.
If not a business, set category to "N/A".
"""


def classify_business(public_text: str) -> dict:
    """
    Classify whether public_text describes a business.

    Returns:
        {
            "is_business": bool,
            "category": str,
            "confidence": float,
            "source": "ai" | "fallback"
        }
    """
    result = _chat(BUSINESS_CLASSIFIER_SYSTEM, public_text[:1500])
    if result and "is_business" in result:
        result["source"] = "ai"
        return result

    # Fallback if API fails
    logger.warning("AI classification failed — returning fallback.")
    return {"is_business": False, "category": "N/A", "confidence": 0.0, "source": "fallback"}


# ── Lead scoring ──────────────────────────────────────────────────────────────

LEAD_SCORER_SYSTEM = """
You are a lead-quality scoring assistant for a web-development agency called Codeloom.
You receive a JSON object with public business information and score how good a lead
this business is for web-development outreach.

Scoring signals (positive):
- No website found in checked public information
- Public business phone or WhatsApp available
- Clear products/services
- Active business presence
- High relevance to web-development services

Scoring signals (negative):
- Uncertain or missing data
- Very low business activity
- Already has a website

Return ONLY valid JSON:
{"score": 0-100, "priority": "HOT"|"GOOD"|"MEDIUM"|"LOW", "reason": "short explanation"}

Priority bands: HOT=90-100, GOOD=70-89, MEDIUM=50-69, LOW=0-49
"""


def score_lead(lead_data: dict) -> dict:
    """
    Score a lead using AI.

    Args:
        lead_data: dict with public business fields (no personal info)

    Returns:
        {"score": int, "priority": str, "reason": str, "source": "ai"|"fallback"}
    """
    # Only pass non-sensitive, business-relevant fields
    safe_fields = {
        "business_name": lead_data.get("business_name"),
        "category":      lead_data.get("category"),
        "website_status": lead_data.get("website_status"),
        "has_phone":     bool(lead_data.get("business_phone")),
        "has_whatsapp":  bool(lead_data.get("business_whatsapp")),
        "country":       lead_data.get("country"),
        "source_post_snippet": (lead_data.get("source_post") or "")[:300],
    }
    result = _chat(LEAD_SCORER_SYSTEM, json.dumps(safe_fields, ensure_ascii=False))
    if result and "score" in result:
        result["source"] = "ai"
        return result

    logger.warning("AI lead scoring failed — returning fallback.")
    return {"score": 0, "priority": "LOW", "reason": "AI scoring unavailable", "source": "fallback"}


# ── Ambiguous website resolution ──────────────────────────────────────────────

WEBSITE_AMBIGUITY_SYSTEM = """
You are a website-detection assistant.
You receive a short text snippet from a public Facebook business page.
Determine if it contains a reference to an external website (not Facebook).

Return ONLY valid JSON:
{"has_website": true/false, "found_url": "url or null", "confidence": 0.0}
"""


def resolve_website_ambiguity(text_snippet: str) -> dict:
    """
    Used when rule-based website detection returns UNCERTAIN.
    Returns: {"has_website": bool, "found_url": str|None, "confidence": float}
    """
    result = _chat(WEBSITE_AMBIGUITY_SYSTEM, text_snippet[:800])
    if result and "has_website" in result:
        return result
    return {"has_website": False, "found_url": None, "confidence": 0.0}
