"""
Phase 12 — Lead Identification Dashboard page.

Accessible at the "Leads" entry in the Streamlit sidebar navigation.
Requires ClickHouse to be running with:
  - analytics.lead_scores_rule_based  (always available — Phase 10 view)
  - analytics.lead_scores_ml          (optional — populated by make score-sessions)
  - analytics.session_features        (always available — Phase 9 view)
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Leads — Lead Intelligence", layout="wide")

# ---------------------------------------------------------------------------
# ClickHouse connection (mirrors app.py pattern)
# ---------------------------------------------------------------------------

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "analytics")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "analytics")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "analytics_password")


@st.cache_resource(show_spinner=False)
def _get_client():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DB,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )


# ---------------------------------------------------------------------------
# Import query helper — works when Streamlit runs from the dashboard/ dir
# ---------------------------------------------------------------------------

try:
    from heatmap_queries import fetch_lead_candidates
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from heatmap_queries import fetch_lead_candidates


# ---------------------------------------------------------------------------
# Helper — rule flags → human-readable string
# ---------------------------------------------------------------------------

_RULE_LABELS: dict[str, str] = {
    "rule_add_to_cart":      "add-to-cart",
    "rule_purchase":         "purchase",
    "rule_browsing_depth":   "deep browse",
    "rule_search_intent":    "search",
    "rule_scroll_engagement":"scroll 70%+",
    "rule_bouncer":          "bouncer",
}


def _rules_fired(row: pd.Series) -> str:
    fired = [label for col, label in _RULE_LABELS.items() if row.get(col, 0) == 1]
    return ", ".join(fired) if fired else "none"


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.title("Lead Candidates")
st.caption(
    "Sessions ranked by purchase-intent score. "
    "Rule score = deterministic rule engine (Phase 10). "
    "ML score = LightGBM probability × 100 (Phase 11)."
)

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    selected_tiers = st.multiselect(
        "Score tier",
        options=["hot", "warm", "cold"],
        default=["hot", "warm"],
        help="hot ≥ 60 · warm ≥ 30 · cold < 30",
    )
    selected_sources = st.multiselect(
        "Source",
        options=["live", "retailrocket"],
        default=["live", "retailrocket"],
    )
    row_limit = st.slider("Max rows", min_value=50, max_value=1000, value=200, step=50)

if not selected_tiers or not selected_sources:
    st.info("Select at least one tier and one source in the sidebar.")
    st.stop()

# Fetch
try:
    client = _get_client()
    df: pd.DataFrame = fetch_lead_candidates(
        client,
        tiers=selected_tiers,
        sources=selected_sources,
        limit=row_limit,
    )
except Exception as exc:
    st.error(f"Failed to connect to ClickHouse: {exc}")
    st.stop()

# Empty state
if df.empty:
    st.info(
        "No leads found for the selected filters. "
        "If analytics.lead_scores_ml is empty, run `make score-sessions` to populate ML scores. "
        "Rule-based scores are always available once ClickHouse views are applied."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Derive display columns
# ---------------------------------------------------------------------------

# ML score as percentage (None when table is empty / session not scored yet)
has_ml = "ml_lead_score" in df.columns and df["ml_lead_score"].notna().any()
if has_ml:
    df["ml_score"] = (df["ml_lead_score"] * 100).round(1)
else:
    df["ml_score"] = None

# Rules-fired summary
df["rules_fired"] = df.apply(_rules_fired, axis=1)

# Cart abandoned: 1/0 → Yes/No
df["cart_abandoned"] = df["cart_abandoned"].map({1: "Yes", 0: "No"}).fillna("No")

# Session duration: seconds → "Xm Ys"
def _fmt_duration(seconds) -> str:
    try:
        s = int(seconds)
        return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"
    except Exception:
        return "—"

df["duration"] = df["session_duration_seconds"].apply(_fmt_duration)

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

tier_counts = df["score_tier"].value_counts()
col_hot, col_warm, col_cold, col_ml = st.columns(4)
col_hot.metric("Hot leads", int(tier_counts.get("hot", 0)))
col_warm.metric("Warm leads", int(tier_counts.get("warm", 0)))
col_cold.metric("Cold leads", int(tier_counts.get("cold", 0)))
col_ml.metric(
    "ML scored",
    f"{df['ml_lead_score'].notna().sum()}" if has_ml else "—",
    help="Sessions with an ML score from analytics.lead_scores_ml",
)

if not has_ml:
    st.warning(
        "ML scores not available — analytics.lead_scores_ml is empty. "
        "Run `make score-sessions` after training the model. "
        "Leads are ranked by rule score only.",
        icon="⚠️",
    )

st.write("---")

# ---------------------------------------------------------------------------
# Ranked leads table
# ---------------------------------------------------------------------------

DISPLAY_COLS = [
    "anonymous_user_id",
    "source",
    "score_tier",
    "rule_score",
    "ml_score",
    "product_views",
    "add_to_cart_count",
    "cart_abandoned",
    "duration",
    "rules_fired",
]

COLUMN_CONFIG = {
    "anonymous_user_id": st.column_config.TextColumn("User ID"),
    "source":            st.column_config.TextColumn("Source"),
    "score_tier": st.column_config.TextColumn(
        "Tier",
        help="hot ≥ 60 · warm ≥ 30 · cold < 30",
    ),
    "rule_score": st.column_config.NumberColumn(
        "Rule score",
        min_value=0,
        max_value=100,
        help="Deterministic rule engine score [0–100]",
    ),
    "ml_score": st.column_config.NumberColumn(
        "ML score",
        min_value=0,
        max_value=100,
        format="%.1f",
        help="LightGBM purchase probability × 100 [0–100]",
    ),
    "product_views":     st.column_config.NumberColumn("Product views"),
    "add_to_cart_count": st.column_config.NumberColumn("Add to cart"),
    "cart_abandoned":    st.column_config.TextColumn("Cart abandoned"),
    "duration":          st.column_config.TextColumn("Session duration"),
    "rules_fired":       st.column_config.TextColumn(
        "Rules fired",
        help="Which scoring rules fired for this session",
    ),
}

st.dataframe(
    df[DISPLAY_COLS],
    use_container_width=True,
    hide_index=True,
    column_config=COLUMN_CONFIG,
)

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

csv_cols = [
    "session_id", "anonymous_user_id", "source", "score_tier",
    "rule_score", "ml_score", "product_views", "add_to_cart_count",
    "cart_abandoned", "session_duration_seconds", "rules_fired",
    "first_event_at", "last_event_at",
]
csv_df = df[[c for c in csv_cols if c in df.columns]]

st.download_button(
    label="Download CSV",
    data=csv_df.to_csv(index=False),
    file_name="leads.csv",
    mime="text/csv",
)
