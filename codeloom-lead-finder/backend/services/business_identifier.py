"""
backend/services/business_identifier.py
─────────────────────────────────────────
Determines whether a candidate is a real business using:
  1. Fast rule-based checks (keywords, category signals)
  2. OpenAI classification for ambiguous cases

Only calls AI when rules return low confidence — keeps costs low.
"""
from __future__ import annotations

import re

from backend.services import ai_service
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── Business category definitions ────────────────────────────────────────────

BUSINESS_CATEGORIES = [
    "Restaurant",
    "Café / Coffee Shop",
    "Retail Shop",
    "Clothing & Fashion",
    "Electronics",
    "Beauty Salon / Spa",
    "Construction & Real Estate",
    "Transport & Logistics",
    "Education & Training",
    "Healthcare & Pharmacy",
    "Food & Beverage",
    "Agriculture",
    "IT & Tech Services",
    "Printing & Design",
    "Hotel & Accommodation",
    "Travel & Tourism",
    "Photography & Media",
    "Auto / Garage",
    "Legal & Consultancy",
    "Other Business",
]

# ── Keyword signals ───────────────────────────────────────────────────────────

_BUSINESS_KEYWORDS = [
    # Offers / services
    r"\bservice[s]?\b", r"\bproduct[s]?\b", r"\bprice[s]?\b", r"\bpric[ei]\w+",
    r"\border\b", r"\bdeliver\w+", r"\bshipping\b", r"\bwholesale\b", r"\bretail\b",
    # Contact / sales
    r"\bcontact\b", r"\bwhatsapp\b", r"\bcall\b", r"\bbook\w+",
    r"\breserv\w+", r"\bappointment\b",
    # Business structure
    r"\bshop\b", r"\bstore\b", r"\bcompan\w+", r"\bagency\b", r"\bsalon\b",
    r"\brestaurant\b", r"\bcaf[eé]\b", r"\bfarm\b", r"\bfactori\w+",
    r"\bconstruct\w+", r"\btransport\b", r"\bpharmac\w+",
    # Bangla / transliterated (common in BD market)
    r"\bdukan\b", r"\bdokan\b", r"\bsell\b", r"\bkena\b", r"\bbecha\b",
]

_COMPILED_KEYWORDS = [re.compile(p, re.IGNORECASE) for p in _BUSINESS_KEYWORDS]

_NON_BUSINESS_SIGNALS = [
    r"\bpersonal\b", r"\bmy life\b", r"\bfamily photo\b", r"\btravel log\b",
    r"\bbirthday\b.*\bwish\b",
]
_COMPILED_NON_BUSINESS = [re.compile(p, re.IGNORECASE) for p in _NON_BUSINESS_SIGNALS]


# ── Rule-based detection ──────────────────────────────────────────────────────

def _rule_score(text: str) -> float:
    """
    Return a simple 0.0–1.0 confidence that the text represents a business.
    Pure rule-based — no AI calls here.
    """
    if not text:
        return 0.0

    # Non-business signals lower confidence
    non_business_hits = sum(1 for p in _COMPILED_NON_BUSINESS if p.search(text))
    if non_business_hits >= 2:
        return 0.05

    # Count keyword hits
    hits = sum(1 for p in _COMPILED_KEYWORDS if p.search(text))
    # Simple sigmoid-like mapping
    if hits >= 5:
        return 0.90
    if hits >= 3:
        return 0.75
    if hits >= 1:
        return 0.55
    return 0.2


def _infer_category(text: str) -> str:
    """Infer a rough category from the text. Returns 'Other Business' if unclear."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["restaurant", "food", "meal", "dinner", "lunch", "catering"]):
        return "Restaurant"
    if any(w in text_lower for w in ["café", "cafe", "coffee", "tea", "bakery"]):
        return "Café / Coffee Shop"
    if any(w in text_lower for w in ["salon", "beauty", "spa", "hair", "makeup"]):
        return "Beauty Salon / Spa"
    if any(w in text_lower for w in ["construction", "build", "real estate", "property", "flat", "apartment"]):
        return "Construction & Real Estate"
    if any(w in text_lower for w in ["transport", "logistics", "courier", "delivery", "truck"]):
        return "Transport & Logistics"
    if any(w in text_lower for w in ["school", "tutor", "coaching", "education", "training", "academy"]):
        return "Education & Training"
    if any(w in text_lower for w in ["pharmacy", "medicine", "clinic", "doctor", "health"]):
        return "Healthcare & Pharmacy"
    if any(w in text_lower for w in ["cloth", "fashion", "dress", "shirt", "garment", "boutique"]):
        return "Clothing & Fashion"
    if any(w in text_lower for w in ["electronic", "mobile", "phone", "laptop", "computer", "gadget"]):
        return "Electronics"
    if any(w in text_lower for w in ["hotel", "resort", "accommodation", "lodge", "guest house"]):
        return "Hotel & Accommodation"
    if any(w in text_lower for w in ["farm", "agri", "crop", "poultry", "fish", "agriculture"]):
        return "Agriculture"
    return "Other Business"


# ── Main public function ──────────────────────────────────────────────────────

CONFIDENCE_THRESHOLD_HIGH = 0.70   # Confident enough — skip AI
CONFIDENCE_THRESHOLD_LOW  = 0.35   # Below this → probably not a business

def identify_business(
    public_text: str,
    category_hint: str | None = None,
    use_ai_for_ambiguous: bool = True,
) -> dict:
    """
    Determine whether the provided public text represents a business.

    Args:
        public_text:          Text from a public Facebook page/post.
        category_hint:        Category string from Facebook if available.
        use_ai_for_ambiguous: Whether to call OpenAI for uncertain cases.

    Returns:
        {
            "is_business": bool,
            "category": str,
            "confidence": float,
            "method": "rules" | "ai" | "hint"
        }
    """
    # 1. If Facebook provides a category, that's strong evidence
    if category_hint and len(category_hint.strip()) > 1:
        logger.debug("Using category hint: %s", category_hint)
        return {
            "is_business": True,
            "category": category_hint.strip(),
            "confidence": 0.90,
            "method": "hint",
        }

    # 2. Rule-based scoring
    rule_conf = _rule_score(public_text)
    logger.debug("Rule-based confidence: %.2f", rule_conf)

    if rule_conf >= CONFIDENCE_THRESHOLD_HIGH:
        return {
            "is_business": True,
            "category": _infer_category(public_text),
            "confidence": rule_conf,
            "method": "rules",
        }

    if rule_conf < CONFIDENCE_THRESHOLD_LOW:
        return {
            "is_business": False,
            "category": "N/A",
            "confidence": rule_conf,
            "method": "rules",
        }

    # 3. Ambiguous — delegate to AI
    if use_ai_for_ambiguous:
        logger.info("Ambiguous case — calling AI classifier.")
        ai_result = ai_service.classify_business(public_text)
        return {
            "is_business": ai_result.get("is_business", False),
            "category":    ai_result.get("category", "Other Business"),
            "confidence":  ai_result.get("confidence", 0.5),
            "method":      "ai",
        }

    # 4. Fallback (AI disabled)
    return {
        "is_business": rule_conf >= 0.5,
        "category": _infer_category(public_text) if rule_conf >= 0.5 else "N/A",
        "confidence": rule_conf,
        "method": "rules",
    }
