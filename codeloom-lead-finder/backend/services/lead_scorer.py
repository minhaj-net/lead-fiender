"""
backend/services/lead_scorer.py
─────────────────────────────────
Scores a lead candidate on a 0–100 scale using rule-based logic.
Optionally augments with AI scoring.

Priority bands:
  HOT    → 90–100
  GOOD   → 70–89
  MEDIUM → 50–69
  LOW    → 0–49

Rule weights (can be tuned after testing real leads):
  No website found              +35
  Has public business phone     +20
  Has public WhatsApp           +15
  Clear business identified     +15
  Active business presence      +10
  Uncertain website             -10
  No contact information        -15
  Failed / uncertain business   -25
"""
from __future__ import annotations

from backend.services import ai_service
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def _priority_from_score(score: int) -> str:
    if score >= 90:
        return "HOT"
    if score >= 70:
        return "GOOD"
    if score >= 50:
        return "MEDIUM"
    return "LOW"


def score_lead_rules(lead_data: dict) -> dict:
    """
    Pure rule-based lead scoring. Fast, no API cost.

    Args:
        lead_data: dict with keys matching Lead fields.

    Returns:
        {"score": int, "priority": str, "reason": str, "method": "rules"}
    """
    score  = 40  # Baseline
    notes  = []

    website_status    = lead_data.get("website_status", "UNCERTAIN")
    has_phone         = bool(lead_data.get("business_phone"))
    has_whatsapp      = bool(lead_data.get("business_whatsapp"))
    is_business       = lead_data.get("is_business", False)
    biz_confidence    = float(lead_data.get("business_confidence", 0.0))

    # ── Positive signals ──────────────────────────────────────────────────────
    if is_business and website_status == "NO":
        score += 35
        notes.append("no website found (+35)")

    if has_phone:
        score += 20
        notes.append("public phone (+20)")

    if has_whatsapp:
        score += 15
        notes.append("public WhatsApp (+15)")

    if is_business and biz_confidence >= 0.75:
        score += 15
        notes.append("clear business (+15)")
    elif is_business and biz_confidence >= 0.5:
        score += 8
        notes.append("likely business (+8)")

    # ── Negative signals ──────────────────────────────────────────────────────
    if website_status == "YES":
        score -= 50
        notes.append("has website (-50)")

    if website_status == "UNCERTAIN":
        score -= 10
        notes.append("website uncertain (-10)")

    if not has_phone and not has_whatsapp:
        score -= 15
        notes.append("no public contact (-15)")

    if not is_business:
        score -= 45
        notes.append("not identified as business (-45)")

    score = max(0, min(100, score))
    priority = _priority_from_score(score)

    reason = "; ".join(notes) if notes else "baseline"
    logger.debug("Rule score=%d priority=%s reason=%s", score, priority, reason)

    return {"score": score, "priority": priority, "reason": reason, "method": "rules"}


def score_lead(lead_data: dict, use_ai: bool = True) -> dict:
    """
    Score a lead, optionally augmenting with AI for mid-range scores.

    Args:
        lead_data: dict with Lead fields plus 'is_business', 'business_confidence'.
        use_ai:    Whether to call OpenAI for borderline scores (50–75).

    Returns:
        {"score": int, "priority": str, "reason": str, "method": str}
    """
    rule_result = score_lead_rules(lead_data)

    # Only call AI for borderline scores to minimize cost
    if use_ai and 50 <= rule_result["score"] <= 75:
        logger.info("Borderline score %d — requesting AI scoring.", rule_result["score"])
        ai_result = ai_service.score_lead(lead_data)
        if ai_result.get("source") == "ai":
            # Blend: rule score 40%, AI score 60% for borderline cases
            blended = int(rule_result["score"] * 0.4 + ai_result["score"] * 0.6)
            blended = max(0, min(100, blended))
            priority = _priority_from_score(blended)
            return {
                "score":    blended,
                "priority": priority,
                "reason":   f"blended (rules: {rule_result['score']}, ai: {ai_result['score']})",
                "method":   "blended",
            }

    return rule_result
