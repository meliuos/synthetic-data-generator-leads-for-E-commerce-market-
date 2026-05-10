"""
Unit tests for Phase 15 prompt_builder and lead_profiler error handling.

These tests are fully offline — no ClickHouse or Anthropic API required.
"""

import pytest

from src.ai.prompt_builder import build_prompt, _MAX_PRODUCTS
from src.ai.lead_profiler import LeadNotFoundError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_context(tier: str, n_products: int = 3) -> dict:
    return {
        "anonymous_user_id": "anon_test_001",
        "score_tier": tier,
        "ml_lead_score": 0.85 if tier == "hot" else (0.45 if tier == "warm" else 0.15),
        "rule_lead_score": 70 if tier == "hot" else (40 if tier == "warm" else 10),
        "top_categories": ["Electronics", "Mobile"],
        "viewed_products": [f"item_{i}" for i in range(n_products)],
        "add_to_cart_count": 3 if tier == "hot" else 0,
        "cart_abandoned": tier == "hot",
        "session_count": 2,
        "avg_scroll_pct": 68.4,
        "search_count": 1,
        "last_active": "2026-04-28T14:32:00+00:00",
    }


# ---------------------------------------------------------------------------
# Template rendering — all tiers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", ["hot", "warm", "cold"])
def test_all_tiers_render(tier: str) -> None:
    ctx = _make_context(tier)
    system_prompt, user_prompt = build_prompt(ctx)
    assert isinstance(system_prompt, str) and len(system_prompt) > 20
    assert isinstance(user_prompt, str) and "anonymous_user_id" in user_prompt


@pytest.mark.parametrize("tier", ["hot", "warm", "cold"])
def test_system_prompt_contains_no_pii(tier: str) -> None:
    ctx = _make_context(tier)
    system_prompt, _ = build_prompt(ctx)
    assert "anon_test_001" not in system_prompt


# ---------------------------------------------------------------------------
# Product list truncation
# ---------------------------------------------------------------------------

def test_viewed_products_truncated_to_max() -> None:
    ctx = _make_context("warm", n_products=_MAX_PRODUCTS + 5)
    assert len(ctx["viewed_products"]) > _MAX_PRODUCTS
    _, user_prompt = build_prompt(ctx)
    import json
    # Extract the JSON blob from the user prompt
    json_part = user_prompt[user_prompt.index("{"):]
    parsed = json.loads(json_part)
    assert len(parsed["viewed_products"]) == _MAX_PRODUCTS


def test_viewed_products_under_max_unchanged() -> None:
    ctx = _make_context("warm", n_products=3)
    _, user_prompt = build_prompt(ctx)
    import json
    parsed = json.loads(user_prompt[user_prompt.index("{"):])
    assert len(parsed["viewed_products"]) == 3


# ---------------------------------------------------------------------------
# Unknown / missing tier falls back to cold
# ---------------------------------------------------------------------------

def test_unknown_tier_falls_back_to_cold() -> None:
    ctx = _make_context("hot")
    ctx["score_tier"] = "unknown_tier"
    system_prompt, _ = build_prompt(ctx)
    cold_system, _ = build_prompt({**ctx, "score_tier": "cold"})
    assert system_prompt == cold_system


# ---------------------------------------------------------------------------
# LeadNotFoundError is an Exception subclass
# ---------------------------------------------------------------------------

def test_lead_not_found_error_is_exception() -> None:
    err = LeadNotFoundError("no data")
    assert isinstance(err, Exception)
    assert "no data" in str(err)


def test_build_script_returns_string_on_missing_lead(monkeypatch) -> None:
    """build_script must return a string, not raise, when lead is missing."""
    import src.ai as ai_module

    def _raise(_uid):
        raise LeadNotFoundError("not found")

    monkeypatch.setattr("src.ai.fetch_lead_context", _raise)
    result = ai_module.build_script("anon_missing")
    assert isinstance(result, str)
    assert len(result) > 0
