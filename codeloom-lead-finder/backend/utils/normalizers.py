"""
backend/utils/normalizers.py
─────────────────────────────
URL and phone-number normalization utilities.
These are deterministic, pure functions — easy to unit-test.
"""
import re
import urllib.parse


# ── URL normalization ──────────────────────────────────────────────────────────

def normalize_url(raw: str | None) -> str | None:
    """
    Clean a raw URL string:
    - Strip whitespace
    - Lowercase scheme + host
    - Remove trailing slashes
    - Remove common tracking params (fbclid, utm_*)
    Returns None if the input is empty/None.
    """
    if not raw:
        return None

    url = raw.strip()
    if not url:
        return None

    # Ensure scheme present so urllib parses correctly
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urllib.parse.urlparse(url)
        # Lowercase scheme and host
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or "/"
        # Strip unwanted query params
        query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
        cleaned_params = {
            k: v
            for k, v in query_params.items()
            if not k.startswith("utm_") and k != "fbclid"
        }
        query_string = urllib.parse.urlencode(cleaned_params, doseq=True)
        normalized = urllib.parse.urlunparse(
            (scheme, netloc, path, parsed.params, query_string, "")
        )
        return normalized
    except Exception:
        return url


def normalize_facebook_url(raw: str | None) -> str | None:
    """
    Normalize a Facebook page/profile URL to a canonical form.
    Example: https://www.facebook.com/MyPage → https://www.facebook.com/mypage
    """
    url = normalize_url(raw)
    if url is None:
        return None
    # Lowercase the full Facebook URL path (page names are case-insensitive)
    try:
        parsed = urllib.parse.urlparse(url)
        if "facebook.com" in parsed.netloc:
            return urllib.parse.urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc.lower(),
                    parsed.path.lower().rstrip("/"),
                    parsed.params,
                    parsed.query,
                    "",
                )
            )
    except Exception:
        pass
    return url


# ── Phone normalization ────────────────────────────────────────────────────────

def normalize_phone(raw: str | None) -> str | None:
    """
    Strip formatting from a phone number, keeping only digits and a leading +.
    Examples:
        "+880 1711-123456" → "+8801711123456"
        "(01711) 123 456"  → "01711123456"
    Returns None if the result is too short to be a real number.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    # Keep leading + for international numbers
    has_plus = cleaned.startswith("+")
    # Remove everything except digits
    digits_only = re.sub(r"[^\d]", "", cleaned)
    if len(digits_only) < 6:
        return None
    return ("+" if has_plus else "") + digits_only


def is_valid_phone(phone: str | None) -> bool:
    """Basic sanity check: 7–15 digits (ITU-T E.164 range)."""
    if not phone:
        return False
    digits = re.sub(r"[^\d]", "", phone)
    return 7 <= len(digits) <= 15


# ── Business name normalization ───────────────────────────────────────────────

def normalize_business_name(raw: str | None) -> str | None:
    """
    Normalize a business name for duplicate-key comparisons.
    Lowercases, strips punctuation and extra whitespace.
    """
    if not raw:
        return None
    name = raw.lower().strip()
    # Remove common noise characters
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name if name else None
