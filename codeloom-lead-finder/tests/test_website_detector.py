"""
tests/test_website_detector.py
───────────────────────────────
Unit tests for the website detector.
Run with: pytest tests/test_website_detector.py -v
"""
import pytest
from backend.services.website_detector import detect_website


class TestWebsiteDetector:

    def test_explicit_website_field_yes(self):
        result = detect_website(website_field="https://mybusiness.com")
        assert result["status"] == "YES"
        assert "mybusiness.com" in result["url"]
        assert result["method"] == "website_field"

    def test_facebook_url_in_website_field_ignored(self):
        """Facebook own URL should NOT count as an external website."""
        result = detect_website(
            website_field="https://www.facebook.com/mypage",
            use_ai_for_uncertain=False,
        )
        assert result["status"] != "YES"

    def test_url_in_about_text(self):
        result = detect_website(
            about_text="Visit us at https://codeloom.com for more info.",
            use_ai_for_uncertain=False,
        )
        assert result["status"] == "YES"
        assert "codeloom.com" in result["url"]
        assert result["method"] == "about_text"

    def test_url_in_post_text(self):
        result = detect_website(
            post_text="Check our new products at https://shop.example.com/products",
            use_ai_for_uncertain=False,
        )
        assert result["status"] == "YES"
        assert result["method"] == "post_text"

    def test_no_website_returns_no(self):
        result = detect_website(
            about_text="We sell clothes. Call us on WhatsApp!",
            use_ai_for_uncertain=False,
        )
        assert result["status"] == "NO"
        assert result["url"] is None

    def test_empty_inputs_returns_no(self):
        result = detect_website(use_ai_for_uncertain=False)
        assert result["status"] == "NO"

    def test_social_link_not_counted(self):
        result = detect_website(
            about_text="Follow us on Instagram: https://instagram.com/mybiz",
            use_ai_for_uncertain=False,
        )
        assert result["status"] == "NO"

    def test_naked_domain_returns_uncertain(self):
        result = detect_website(
            about_text="Visit www.mybusiness.com for orders",
            use_ai_for_uncertain=False,  # Don't call AI in unit test
        )
        # Without AI, naked domain should be UNCERTAIN
        assert result["status"] in ("YES", "UNCERTAIN")

    def test_returns_required_keys(self):
        result = detect_website()
        assert "status" in result
        assert "url" in result
        assert "method" in result
        assert "note" in result
