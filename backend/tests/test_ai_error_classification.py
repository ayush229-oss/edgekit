"""
Regression tests for _normalize_api_error (backend/api/routes_graph_v2.py).

Why this file exists: the classifier used to test for the bare substring
"rate" when deciding whether a provider error was a rate limit. Gemini's REST
method is `generateContent`, and "gene-RATE" contains "rate" -- so a bad model
name, a disabled API, or a billing misconfiguration all came back to the user
as "gemini rate limit hit. Wait a minute and try again."

That is worse than an unhelpful message: it actively misdirects. The operator
sees "rate limit", assumes quota exhaustion, and goes looking at billing --
which in the incident that prompted these tests was already enabled and
perfectly healthy. The true error stayed invisible the whole time.

The rule these tests defend: a message is only a rate limit if it actually
says so. Anything unrecognised must fall through to 502 carrying the raw
provider text, so the real cause reaches whoever is debugging.
"""

import pytest

from backend.api.routes_graph_v2 import _normalize_api_error


# Real provider strings that contain "generate" (and therefore "rate") but are
# emphatically NOT rate limits. Each must survive as a 502 with its own text.
NOT_RATE_LIMITS = [
    "models/gemini-2.5-flash is not found for API version v1beta, "
    "or is not supported for generateContent",
    "Failed to generate content: the model is unavailable",
    "generateContent request failed: internal error",
    "Billing account not configured for generateContent",
    "Publisher Model is not available in your project",
]

# Genuine throttling / exhaustion messages, which must classify as 429.
REAL_RATE_LIMITS = [
    "429 Too Many Requests",
    "Rate limit reached for gemini-2.5-flash",
    "You exceeded your current quota, please check your plan",
    "RESOURCE_EXHAUSTED: quota exceeded",
    "rate_limit_exceeded",
]


@pytest.mark.parametrize("msg", NOT_RATE_LIMITS)
def test_generate_content_errors_are_not_reported_as_rate_limits(msg):
    """The exact bug: "generate" must not read as "rate"."""
    exc = _normalize_api_error("gemini", msg)
    assert exc.status_code != 429, (
        f"{msg!r} was misclassified as a rate limit -- the substring check is "
        "matching a bare 'rate' again."
    )


@pytest.mark.parametrize("msg", NOT_RATE_LIMITS)
def test_unrecognised_errors_surface_the_raw_provider_text(msg):
    """A 502 must carry the provider's own words, or debugging is blind."""
    exc = _normalize_api_error("gemini", msg)
    assert exc.status_code == 502
    # The first few words of the real error have to survive into the detail.
    assert msg[:30] in exc.detail


@pytest.mark.parametrize("msg", REAL_RATE_LIMITS)
def test_genuine_rate_limits_still_classify_as_429(msg):
    """Tightening the match must not break the case it was there to catch."""
    assert _normalize_api_error("gemini", msg).status_code == 429


def test_invalid_key_is_a_400_not_a_rate_limit():
    exc = _normalize_api_error("gemini", "API_KEY_INVALID: the API key is invalid")
    assert exc.status_code == 400


def test_permission_errors_classify_as_403():
    exc = _normalize_api_error("gemini", "PERMISSION_DENIED on this model")
    assert exc.status_code == 403
