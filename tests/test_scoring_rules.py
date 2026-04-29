"""
Unit tests for src/scoring/rules.py — Phase 10 rule-based lead scoring.

Tests cover:
  - Each rule fires independently and contributes the correct delta.
  - Combined rules sum correctly.
  - Score floor (0): negative raw scores are clamped to 0.
  - Score ceiling (100): scores above 100 are clamped to 100.
  - Tier classification at all three tiers, including exact boundary values.
  - Edge cases: None max_scroll_pct, Retailrocket source, direct-buy (purchase without prior cart).
  - Batch scoring via score_sessions().
  - from_dict constructor handles all column types including None for Nullable.
"""

import sys
import unittest
from pathlib import Path

# Allow running tests from project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scoring.rules import (
    TIER_HOT_MIN,
    TIER_WARM_MIN,
    LeadScore,
    SessionFeatures,
    score_session,
    score_sessions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session(**overrides) -> SessionFeatures:
    """
    Return a minimal cold session with all signals off.
    Override individual fields to exercise specific rules.
    """
    defaults = dict(
        session_id="test-session",
        anonymous_user_id="anon-123",
        page_views=2,          # > 1 so bouncer rule does NOT fire by default
        product_views=0,
        add_to_cart_count=0,
        purchase_count=0,
        search_count=0,
        max_scroll_pct=None,
        session_duration_seconds=30,
        distinct_products_viewed=0,
        cart_abandoned=0,
        source="live",
    )
    defaults.update(overrides)
    return SessionFeatures(**defaults)


# ---------------------------------------------------------------------------
# Individual rule tests
# ---------------------------------------------------------------------------

class TestAddToCartRule(unittest.TestCase):
    def test_fires_when_cart_count_positive(self):
        result = score_session(_session(add_to_cart_count=1))
        self.assertIn("add_to_cart", result.rule_contributions)
        self.assertEqual(result.rule_contributions["add_to_cart"], 30)

    def test_does_not_fire_when_cart_count_zero(self):
        result = score_session(_session(add_to_cart_count=0))
        self.assertNotIn("add_to_cart", result.rule_contributions)


class TestPurchaseRule(unittest.TestCase):
    def test_fires_when_purchase_count_positive(self):
        result = score_session(_session(purchase_count=1))
        self.assertIn("purchase", result.rule_contributions)
        self.assertEqual(result.rule_contributions["purchase"], 20)

    def test_does_not_fire_when_purchase_count_zero(self):
        result = score_session(_session(purchase_count=0))
        self.assertNotIn("purchase", result.rule_contributions)

    def test_direct_buy_no_cart(self):
        """Purchase without add_to_cart (direct buy): +20 only, no +30."""
        result = score_session(_session(purchase_count=1, add_to_cart_count=0))
        self.assertEqual(result.lead_score, 20)
        self.assertIn("purchase", result.rule_contributions)
        self.assertNotIn("add_to_cart", result.rule_contributions)
        self.assertEqual(result.score_tier, "cold")  # 20 < TIER_WARM_MIN (30)


class TestBrowsingDepthRule(unittest.TestCase):
    def test_fires_at_exactly_three_products(self):
        result = score_session(_session(distinct_products_viewed=3))
        self.assertIn("browsing_depth", result.rule_contributions)
        self.assertEqual(result.rule_contributions["browsing_depth"], 15)

    def test_fires_above_three(self):
        result = score_session(_session(distinct_products_viewed=10))
        self.assertIn("browsing_depth", result.rule_contributions)

    def test_does_not_fire_below_three(self):
        result = score_session(_session(distinct_products_viewed=2))
        self.assertNotIn("browsing_depth", result.rule_contributions)

    def test_does_not_fire_at_zero(self):
        result = score_session(_session(distinct_products_viewed=0))
        self.assertNotIn("browsing_depth", result.rule_contributions)


class TestSearchIntentRule(unittest.TestCase):
    def test_fires_when_search_count_positive(self):
        result = score_session(_session(search_count=1))
        self.assertIn("search_intent", result.rule_contributions)
        self.assertEqual(result.rule_contributions["search_intent"], 10)

    def test_does_not_fire_when_search_count_zero(self):
        result = score_session(_session(search_count=0))
        self.assertNotIn("search_intent", result.rule_contributions)


class TestScrollEngagementRule(unittest.TestCase):
    def test_fires_when_scroll_above_70(self):
        result = score_session(_session(max_scroll_pct=75.0))
        self.assertIn("scroll_engagement", result.rule_contributions)
        self.assertEqual(result.rule_contributions["scroll_engagement"], 10)

    def test_fires_just_above_threshold(self):
        result = score_session(_session(max_scroll_pct=70.01))
        self.assertIn("scroll_engagement", result.rule_contributions)

    def test_does_not_fire_at_exactly_70(self):
        result = score_session(_session(max_scroll_pct=70.0))
        self.assertNotIn("scroll_engagement", result.rule_contributions)

    def test_does_not_fire_when_scroll_below_70(self):
        result = score_session(_session(max_scroll_pct=50.0))
        self.assertNotIn("scroll_engagement", result.rule_contributions)

    def test_does_not_fire_when_scroll_pct_is_none(self):
        """None means no scroll events — must NOT fire, must NOT raise."""
        result = score_session(_session(max_scroll_pct=None))
        self.assertNotIn("scroll_engagement", result.rule_contributions)


class TestBouncerRule(unittest.TestCase):
    def _bounce(self) -> SessionFeatures:
        return _session(
            page_views=1,
            product_views=0,
            add_to_cart_count=0,
            purchase_count=0,
            search_count=0,
        )

    def test_fires_on_strict_bounce(self):
        result = score_session(self._bounce())
        self.assertIn("bouncer", result.rule_contributions)
        self.assertEqual(result.rule_contributions["bouncer"], -10)

    def test_does_not_fire_when_page_views_gt_1(self):
        result = score_session(_session(page_views=2))
        self.assertNotIn("bouncer", result.rule_contributions)

    def test_does_not_fire_when_product_views_present(self):
        result = score_session(_session(page_views=1, product_views=1))
        self.assertNotIn("bouncer", result.rule_contributions)

    def test_does_not_fire_when_add_to_cart_present(self):
        result = score_session(_session(page_views=1, add_to_cart_count=1))
        self.assertNotIn("bouncer", result.rule_contributions)

    def test_does_not_fire_when_purchase_present(self):
        result = score_session(_session(page_views=1, purchase_count=1))
        self.assertNotIn("bouncer", result.rule_contributions)

    def test_does_not_fire_when_search_present(self):
        result = score_session(_session(page_views=1, search_count=1))
        self.assertNotIn("bouncer", result.rule_contributions)


# ---------------------------------------------------------------------------
# Score combination tests
# ---------------------------------------------------------------------------

class TestScoreCombinations(unittest.TestCase):
    def test_all_signals_present_max_score(self):
        """All positive rules fire → 30+20+15+10+10 = 85 (< 100 cap)."""
        result = score_session(_session(
            add_to_cart_count=1,
            purchase_count=1,
            distinct_products_viewed=5,
            search_count=2,
            max_scroll_pct=90.0,
        ))
        self.assertEqual(result.lead_score, 85)
        self.assertEqual(result.score_tier, "hot")
        self.assertEqual(len(result.rule_contributions), 5)  # all positive rules
        self.assertNotIn("bouncer", result.rule_contributions)

    def test_add_to_cart_only_is_warm(self):
        """30 pts from add_to_cart only → warm (exactly at boundary)."""
        result = score_session(_session(add_to_cart_count=1))
        self.assertEqual(result.lead_score, 30)
        self.assertEqual(result.score_tier, "warm")

    def test_purchase_only_is_cold(self):
        """20 pts from purchase only → cold (below warm threshold of 30)."""
        result = score_session(_session(purchase_count=1))
        self.assertEqual(result.lead_score, 20)
        self.assertEqual(result.score_tier, "cold")

    def test_add_to_cart_plus_purchase_is_warm(self):
        """30 + 20 = 50 → warm."""
        result = score_session(_session(add_to_cart_count=1, purchase_count=1))
        self.assertEqual(result.lead_score, 50)
        self.assertEqual(result.score_tier, "warm")

    def test_hot_tier_via_cart_purchase_browsing(self):
        """30 + 20 + 15 = 65 → hot."""
        result = score_session(_session(
            add_to_cart_count=1,
            purchase_count=1,
            distinct_products_viewed=3,
        ))
        self.assertEqual(result.lead_score, 65)
        self.assertEqual(result.score_tier, "hot")

    def test_hot_exact_boundary_via_cart_purchase_search(self):
        """30 + 20 + 10 = 60 → hot (exactly at TIER_HOT_MIN)."""
        result = score_session(_session(
            add_to_cart_count=1,
            purchase_count=1,
            search_count=1,
        ))
        self.assertEqual(result.lead_score, 60)
        self.assertEqual(result.score_tier, "hot")
        self.assertGreaterEqual(result.lead_score, TIER_HOT_MIN)


# ---------------------------------------------------------------------------
# Floor and ceiling tests
# ---------------------------------------------------------------------------

class TestScoreClamping(unittest.TestCase):
    def test_floor_bouncer_only_session(self):
        """Bouncer (-10) alone → clamped to 0, not -10."""
        result = score_session(_session(
            page_views=1,
            product_views=0,
            add_to_cart_count=0,
            purchase_count=0,
            search_count=0,
        ))
        self.assertEqual(result.lead_score, 0)  # floor applied
        self.assertEqual(result.score_tier, "cold")
        self.assertIn("bouncer", result.rule_contributions)

    def test_zero_signal_session_scores_zero(self):
        """No rules fire → raw 0 → clamped 0."""
        result = score_session(_session())  # default: all signals off, page_views=2
        self.assertEqual(result.lead_score, 0)
        self.assertEqual(result.score_tier, "cold")
        self.assertEqual(result.rule_contributions, {})

    def test_ceiling_is_100(self):
        """
        Current max is 85, but verify the ceiling logic works by testing that
        adding more signals beyond 100 would be clamped. We do this by checking
        the maximum achievable score does NOT exceed 100.
        """
        result = score_session(_session(
            add_to_cart_count=5,
            purchase_count=3,
            distinct_products_viewed=10,
            search_count=7,
            max_scroll_pct=99.0,
        ))
        self.assertLessEqual(result.lead_score, 100)
        self.assertEqual(result.lead_score, 85)  # current max with all rules


# ---------------------------------------------------------------------------
# Tier boundary tests
# ---------------------------------------------------------------------------

class TestTierBoundaries(unittest.TestCase):
    def test_warm_min_boundary(self):
        """Score at exactly TIER_WARM_MIN → warm."""
        self.assertEqual(TIER_WARM_MIN, 30)
        result = score_session(_session(add_to_cart_count=1))  # exactly 30
        self.assertEqual(result.lead_score, 30)
        self.assertEqual(result.score_tier, "warm")

    def test_hot_min_boundary(self):
        """Score at exactly TIER_HOT_MIN → hot."""
        self.assertEqual(TIER_HOT_MIN, 60)
        result = score_session(_session(
            add_to_cart_count=1,   # +30
            purchase_count=1,      # +20
            search_count=1,        # +10  → total 60
        ))
        self.assertEqual(result.lead_score, 60)
        self.assertEqual(result.score_tier, "hot")

    def test_just_below_warm_is_cold(self):
        """20 pts → cold (just below TIER_WARM_MIN of 30)."""
        result = score_session(_session(purchase_count=1))  # +20 only
        self.assertEqual(result.lead_score, 20)
        self.assertEqual(result.score_tier, "cold")

    def test_just_below_hot_is_warm(self):
        """50 pts → warm (just below TIER_HOT_MIN of 60)."""
        result = score_session(_session(add_to_cart_count=1, purchase_count=1))
        self.assertEqual(result.lead_score, 50)
        self.assertEqual(result.score_tier, "warm")


# ---------------------------------------------------------------------------
# Retailrocket source test
# ---------------------------------------------------------------------------

class TestRetailrocketSource(unittest.TestCase):
    def test_retailrocket_session_with_product_views_and_cart(self):
        """
        Retailrocket sessions have page_views=0 and search_count=0 by design.
        Bouncer rule must NOT fire (page_views != 1).
        """
        result = score_session(_session(
            source="retailrocket",
            page_views=0,          # always 0 for Retailrocket
            search_count=0,        # always 0 for Retailrocket
            product_views=5,
            distinct_products_viewed=5,
            add_to_cart_count=2,
        ))
        self.assertNotIn("bouncer", result.rule_contributions)
        self.assertIn("add_to_cart", result.rule_contributions)
        self.assertIn("browsing_depth", result.rule_contributions)
        self.assertEqual(result.lead_score, 45)   # 30 + 15
        self.assertEqual(result.score_tier, "warm")
        self.assertEqual(result.source, "retailrocket")

    def test_retailrocket_converted_session(self):
        """Retailrocket transaction → purchase rule fires."""
        result = score_session(_session(
            source="retailrocket",
            page_views=0,
            search_count=0,
            product_views=3,
            distinct_products_viewed=3,
            add_to_cart_count=1,
            purchase_count=1,
        ))
        self.assertIn("purchase", result.rule_contributions)
        self.assertIn("add_to_cart", result.rule_contributions)
        self.assertIn("browsing_depth", result.rule_contributions)
        self.assertEqual(result.lead_score, 65)   # 30 + 20 + 15
        self.assertEqual(result.score_tier, "hot")


# ---------------------------------------------------------------------------
# Batch scoring test
# ---------------------------------------------------------------------------

class TestScoreSessions(unittest.TestCase):
    def test_returns_one_result_per_input(self):
        sessions = [
            _session(session_id="s1", add_to_cart_count=1),
            _session(session_id="s2", purchase_count=1),
            _session(session_id="s3"),
        ]
        results = score_sessions(sessions)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].session_id, "s1")
        self.assertEqual(results[1].session_id, "s2")
        self.assertEqual(results[2].session_id, "s3")

    def test_order_is_preserved(self):
        sessions = [_session(session_id=str(i)) for i in range(10)]
        results = score_sessions(sessions)
        for i, r in enumerate(results):
            self.assertEqual(r.session_id, str(i))

    def test_empty_iterable_returns_empty_list(self):
        self.assertEqual(score_sessions([]), [])


# ---------------------------------------------------------------------------
# from_dict constructor tests
# ---------------------------------------------------------------------------

class TestFromDict(unittest.TestCase):
    def _row(self, **overrides) -> dict:
        base = {
            "session_id": "sess-abc",
            "anonymous_user_id": "anon-xyz",
            "page_views": 3,
            "product_views": 2,
            "add_to_cart_count": 1,
            "purchase_count": 0,
            "search_count": 1,
            "max_scroll_pct": 55.5,
            "session_duration_seconds": 120,
            "distinct_products_viewed": 2,
            "cart_abandoned": 1,
            "source": "live",
        }
        base.update(overrides)
        return base

    def test_constructs_from_full_row(self):
        f = SessionFeatures.from_dict(self._row())
        self.assertEqual(f.session_id, "sess-abc")
        self.assertEqual(f.add_to_cart_count, 1)
        self.assertAlmostEqual(f.max_scroll_pct, 55.5)
        self.assertEqual(f.source, "live")

    def test_none_max_scroll_pct_is_preserved(self):
        """Nullable(Float32) NULL from ClickHouse → None in Python."""
        f = SessionFeatures.from_dict(self._row(max_scroll_pct=None))
        self.assertIsNone(f.max_scroll_pct)
        # verify scroll_engagement rule does not fire
        result = score_session(f)
        self.assertNotIn("scroll_engagement", result.rule_contributions)

    def test_integer_columns_cast_correctly(self):
        f = SessionFeatures.from_dict(self._row(page_views=1, product_views=0))
        self.assertIsInstance(f.page_views, int)
        self.assertIsInstance(f.product_views, int)

    def test_source_preserved(self):
        f = SessionFeatures.from_dict(self._row(source="retailrocket"))
        self.assertEqual(f.source, "retailrocket")


if __name__ == "__main__":
    unittest.main()
