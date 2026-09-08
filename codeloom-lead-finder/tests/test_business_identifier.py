"""
tests/test_business_identifier.py
───────────────────────────────────
Unit tests for the rule-based business identifier.
Run with: pytest tests/test_business_identifier.py -v
"""
import pytest
from backend.services.business_identifier import identify_business


class TestBusinessIdentifier:

    def test_clear_business_by_hint(self):
        result = identify_business(
            public_text="Some text",
            category_hint="Restaurant",
            use_ai_for_ambiguous=False,
        )
        assert result["is_business"] is True
        assert result["category"] == "Restaurant"
        assert result["confidence"] >= 0.85
        assert result["method"] == "hint"

    def test_keyword_rich_text_is_business(self):
        text = (
            "We offer delivery service for all products. "
            "Contact us on WhatsApp to place your order. "
            "Wholesale and retail available."
        )
        result = identify_business(text, use_ai_for_ambiguous=False)
        assert result["is_business"] is True
        assert result["confidence"] >= 0.70

    def test_personal_post_not_business(self):
        text = "My personal life updates and family photo albums."
        result = identify_business(text, use_ai_for_ambiguous=False)
        # Should be low confidence — not clearly a business
        assert result["confidence"] < 0.5

    def test_restaurant_category_inference(self):
        text = "Best restaurant in town. Come enjoy our dinner and lunch menu!"
        result = identify_business(text, use_ai_for_ambiguous=False)
        if result["is_business"]:
            assert result["category"] in ("Restaurant", "Other Business")

    def test_beauty_salon_category_inference(self):
        text = "Professional beauty salon. Hair, makeup, spa services available."
        result = identify_business(text, use_ai_for_ambiguous=False)
        if result["is_business"]:
            assert result["category"] in ("Beauty Salon / Spa", "Other Business")

    def test_empty_text(self):
        result = identify_business("", use_ai_for_ambiguous=False)
        assert result["is_business"] is False
        assert result["confidence"] < 0.5

    def test_returns_required_keys(self):
        result = identify_business("Buy our products!", use_ai_for_ambiguous=False)
        assert "is_business" in result
        assert "category" in result
        assert "confidence" in result
        assert "method" in result
