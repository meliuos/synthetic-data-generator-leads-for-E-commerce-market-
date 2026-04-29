"""
Rule-based lead scoring engine.

Applies a deterministic rule table to a SessionFeatures vector and returns a
clamped [0, 100] lead score with a per-rule contribution breakdown.

Design constraints:
  - No external dependencies — importable without ClickHouse or ML libraries.
  - Rules are data, not code: each entry is (name, delta, predicate). Add, remove,
    or tune a rule by editing _RULES; tests and the ClickHouse view must stay in sync.
  - The Python module and the ClickHouse view analytics.lead_scores_rule_based apply
    the SAME logic. Keep them in sync when modifying thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional


# ---------------------------------------------------------------------------
# Tier thresholds — must match the ClickHouse view definition
# ---------------------------------------------------------------------------

TIER_HOT_MIN: int = 60
TIER_WARM_MIN: int = 30


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionFeatures:
    """
    Mirrors the schema of analytics.session_features (Phase 9 view).

    Field notes:
      max_scroll_pct   — None when the session has no scroll events (not 0.0).
                         This distinction matters for the scroll_engagement rule.
      cart_abandoned   — 1 if add_to_cart fired but purchase never did; else 0.
      source           — 'live' | 'retailrocket'
    """

    session_id: str
    anonymous_user_id: str
    page_views: int
    product_views: int
    add_to_cart_count: int
    purchase_count: int
    search_count: int
    max_scroll_pct: Optional[float]
    session_duration_seconds: int
    distinct_products_viewed: int
    cart_abandoned: int
    source: str

    @classmethod
    def from_dict(cls, row: dict) -> "SessionFeatures":
        """
        Construct from a clickhouse_connect result-row dict.

        clickhouse_connect returns:
          - Integer columns as Python int
          - Nullable(Float32) as float or None
          - String/LowCardinality as str
        """
        scroll_raw = row.get("max_scroll_pct")
        return cls(
            session_id=str(row["session_id"]),
            anonymous_user_id=str(row["anonymous_user_id"]),
            page_views=int(row["page_views"]),
            product_views=int(row["product_views"]),
            add_to_cart_count=int(row["add_to_cart_count"]),
            purchase_count=int(row["purchase_count"]),
            search_count=int(row["search_count"]),
            max_scroll_pct=float(scroll_raw) if scroll_raw is not None else None,
            session_duration_seconds=int(row["session_duration_seconds"]),
            distinct_products_viewed=int(row["distinct_products_viewed"]),
            cart_abandoned=int(row["cart_abandoned"]),
            source=str(row["source"]),
        )


@dataclass(frozen=True)
class LeadScore:
    """
    Output of score_session().

    rule_contributions maps each fired rule name to its delta.
    Rules that did NOT fire are absent from the dict (not present with delta 0).
    This allows the Phase 12 dashboard to show exactly which signals drove the score.
    """

    session_id: str
    anonymous_user_id: str
    lead_score: int                    # clamped to [0, 100]
    score_tier: str                    # 'hot' | 'warm' | 'cold'
    rule_contributions: dict[str, int] # rule_name → delta for fired rules only
    source: str


# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

_SCORE_FLOOR = 0
_SCORE_CEIL = 100

# ---------------------------------------------------------------------------
# Rule table
#
# Each entry: (name, delta, predicate).
#   name      — stable identifier, mirrored in the ClickHouse view column names.
#   delta     — integer score change when the predicate is true (may be negative).
#   predicate — pure function of SessionFeatures, must not raise.
#
# Rules are evaluated independently (not mutually exclusive). The final score is
# the sum of all fired deltas, clamped to [_SCORE_FLOOR, _SCORE_CEIL].
#
# Maximum achievable score: 30 + 20 + 15 + 10 + 10 = 85
# Minimum before floor: -10 (bouncer only) → clamped to 0
# ---------------------------------------------------------------------------

_RuleEntry = tuple[str, int, Callable[[SessionFeatures], bool]]

_RULES: list[_RuleEntry] = [
    (
        # Strong purchase-intent signal: visitor placed something in the cart.
        "add_to_cart",
        +30,
        lambda f: f.add_to_cart_count > 0,
    ),
    (
        # Already converted — high-value candidate for repeat engagement.
        "purchase",
        +20,
        lambda f: f.purchase_count > 0,
    ),
    (
        # Deep browsing: viewed 3+ distinct products → deliberate evaluation.
        "browsing_depth",
        +15,
        lambda f: f.distinct_products_viewed >= 3,
    ),
    (
        # Active search intent: visitor looked for something specific.
        "search_intent",
        +10,
        lambda f: f.search_count > 0,
    ),
    (
        # High scroll engagement: scrolled past 70% of page content.
        # None means no scroll events at all — does NOT fire the rule.
        "scroll_engagement",
        +10,
        lambda f: f.max_scroll_pct is not None and f.max_scroll_pct > 70.0,
    ),
    (
        # Bouncer: exactly one page view and zero e-commerce signals.
        # Penalises sessions with no engagement value for lead generation.
        # Only fires when ALL conditions are true simultaneously.
        "bouncer",
        -10,
        lambda f: (
            f.page_views == 1
            and f.add_to_cart_count == 0
            and f.purchase_count == 0
            and f.search_count == 0
            and f.product_views == 0
        ),
    ),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tier(score: int) -> str:
    """Map a clamped score to a human-readable tier label."""
    if score >= TIER_HOT_MIN:
        return "hot"
    if score >= TIER_WARM_MIN:
        return "warm"
    return "cold"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_session(features: SessionFeatures) -> LeadScore:
    """
    Apply all rules and return a clamped lead score with a contribution breakdown.

    Only rules that fired appear in rule_contributions. This makes the output
    self-explaining: an empty dict means no positive OR negative signals fired.
    """
    raw = 0
    contributions: dict[str, int] = {}

    for name, delta, predicate in _RULES:
        if predicate(features):
            raw += delta
            contributions[name] = delta

    clamped = max(_SCORE_FLOOR, min(_SCORE_CEIL, raw))

    return LeadScore(
        session_id=features.session_id,
        anonymous_user_id=features.anonymous_user_id,
        lead_score=clamped,
        score_tier=_tier(clamped),
        rule_contributions=contributions,
        source=features.source,
    )


def score_sessions(features_iter: Iterable[SessionFeatures]) -> list[LeadScore]:
    """Score a batch of sessions. Order of output matches order of input."""
    return [score_session(f) for f in features_iter]
