"""
tests/test_lead_scorer.py
──────────────────────────
Unit tests for the rule-based lead scorer.
Run with: pytest tests/test_lead_scorer.py -v
"""
import pytest
from backend.services.lead_scorer import score_lead_rules, _priority_from_score


class TestPriorityFromScore:

    def test_hot(self):
        assert _priority_from_score(95) == "HOT"
        assert _priority_from_score(90) == "HOT"

    def test_good(self):
        assert _priority_from_score(89) == "GOOD"
        assert _priority_from_score(70) == "GOOD"

    def test_medium(self):
        assert _priority_from_score(69) == "MEDIUM"
        assert _priority_from_score(50) == "MEDIUM"

    def test_low(self):
        assert _priority_from_score(49) == "LOW"
        assert _priority_from_score(0)  == "LOW"


class TestScoreLeadRules:

    def _make_lead(self, **kwargs) -> dict:
        defaults = {
            "website_status":      "NO",
            "business_phone":      "+8801711123456",
            "business_whatsapp":   "+8801711123456",
            "is_business":         True,
            "business_confidence": 0.9,
        }
        return {**defaults, **kwargs}

    def test_ideal_lead_high_score(self):
        """No website + phone + WhatsApp + clear business = high score."""
        result = score_lead_rules(self._make_lead())
        assert result["score"] >= 80
        assert result["priority"] in ("HOT", "GOOD")

    def test_has_website_low_score(self):
        """Lead with a website should score very low."""
        result = score_lead_rules(self._make_lead(website_status="YES"))
        assert result["score"] < 50

    def test_no_contact_info_lowers_score(self):
        base    = score_lead_rules(self._make_lead())
        no_contact = score_lead_rules(self._make_lead(business_phone=None, business_whatsapp=None))
        assert no_contact["score"] < base["score"]

    def test_not_business_very_low_score(self):
        result = score_lead_rules(self._make_lead(is_business=False))
        assert result["score"] < 40

    def test_score_clamped_0_to_100(self):
        result = score_lead_rules(self._make_lead())
        assert 0 <= result["score"] <= 100

    def test_returns_required_keys(self):
        result = score_lead_rules(self._make_lead())
        assert "score" in result
        assert "priority" in result
        assert "reason" in result
        assert "method" in result
        assert result["method"] == "rules"
