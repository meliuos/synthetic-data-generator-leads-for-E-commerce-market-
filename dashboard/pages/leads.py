"""
Phase 12 + 16 — Lead Identification Dashboard page.

Phase 12: ranked leads table with rule + ML scores.
Phase 16: per-lead AI script generation via OpenRouter + script history panel.

Accessible at the "Leads" entry in the Streamlit sidebar navigation.
Requires ClickHouse to be running with:
  - analytics.lead_scores_rule_based  (Phase 10)
  - analytics.lead_scores_ml          (Phase 11 — optional)
  - analytics.session_features        (Phase 9)
  - analytics.ai_script_log           (Phase 15 — optional, for script history)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Leads — Lead Intelligence", layout="wide")

# ---------------------------------------------------------------------------
# Repo root on sys.path so src/ai is importable from the dashboard process
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# ClickHouse connection
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
# Import query helper
# ---------------------------------------------------------------------------

try:
    from heatmap_queries import fetch_lead_candidates
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from heatmap_queries import fetch_lead_candidates


# ---------------------------------------------------------------------------
# Helper — rule flags → human-readable string
# ---------------------------------------------------------------------------

_RULE_LABELS: dict[str, str] = {
    "rule_add_to_cart":       "add-to-cart",
    "rule_purchase":          "purchase",
    "rule_browsing_depth":    "deep browse",
    "rule_search_intent":     "search",
    "rule_scroll_engagement": "scroll 70%+",
    "rule_bouncer":           "bouncer",
}


def _rules_fired(row: pd.Series) -> str:
    fired = [label for col, label in _RULE_LABELS.items() if row.get(col, 0) == 1]
    return ", ".join(fired) if fired else "none"


# ---------------------------------------------------------------------------
# Phase 16 helpers — script generation
# ---------------------------------------------------------------------------

_SENTINEL_NOT_FOUND = "No behavioral data found"
_SENTINEL_TIMEOUT = "timed out"


def _call_build_script(anonymous_user_id: str) -> str:
    """Lazy import so the dashboard works even without src/ai deps installed."""
    try:
        from src.ai import build_script
        return build_script(anonymous_user_id)
    except ImportError as exc:
        return (
            f"AI dependencies not installed: {exc}. "
            "Run: pip install -r requirements-ai.txt"
        )


def _fetch_script_log(client) -> pd.DataFrame:
    try:
        result = client.query(
            """
            SELECT
                lead_id,
                tier,
                model,
                prompt_tokens   AS prompt_chars,
                output_tokens   AS response_chars,
                generated_at
            FROM analytics.ai_script_log
            ORDER BY generated_at DESC
            LIMIT 10
            """
        )
        return pd.DataFrame(result.result_rows, columns=result.column_names)
    except Exception:
        return pd.DataFrame()


def _fetch_last_log_entry(client, anonymous_user_id: str) -> dict | None:
    try:
        result = client.query(
            """
            SELECT model, prompt_tokens, output_tokens, generated_at
            FROM analytics.ai_script_log
            WHERE lead_id = {uid:String}
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            parameters={"uid": anonymous_user_id},
        )
        if result.result_rows:
            return dict(zip(result.column_names, result.result_rows[0]))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.title("Lead Candidates")
st.caption(
    "Sessions ranked by purchase-intent score. "
    "Rule score = deterministic rule engine (Phase 10). "
    "ML score = LightGBM probability × 100 (Phase 11). "
    "AI scripts powered by OpenRouter free-tier LLM (Phase 16)."
)

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

if df.empty:
    st.info(
        "No leads found for the selected filters. "
        "If analytics.lead_scores_ml is empty, run `make score-sessions` to populate ML scores."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Derive display columns
# ---------------------------------------------------------------------------

has_ml = "ml_lead_score" in df.columns and df["ml_lead_score"].notna().any()
df["ml_score"] = (df["ml_lead_score"] * 100).round(1) if has_ml else None
df["rules_fired"] = df.apply(_rules_fired, axis=1)
df["cart_abandoned"] = df["cart_abandoned"].map({1: "Yes", 0: "No"}).fillna("No")


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
        "ML scores not available — run `make score-sessions` after training the model.",
        icon="⚠️",
    )

st.write("---")

# ---------------------------------------------------------------------------
# Ranked leads table
# ---------------------------------------------------------------------------

DISPLAY_COLS = [
    "anonymous_user_id", "source", "score_tier", "rule_score", "ml_score",
    "product_views", "add_to_cart_count", "cart_abandoned", "duration", "rules_fired",
]
COLUMN_CONFIG = {
    "anonymous_user_id": st.column_config.TextColumn("User ID"),
    "source":            st.column_config.TextColumn("Source"),
    "score_tier":        st.column_config.TextColumn("Tier", help="hot ≥ 60 · warm ≥ 30 · cold < 30"),
    "rule_score":        st.column_config.NumberColumn("Rule score", min_value=0, max_value=100),
    "ml_score":          st.column_config.NumberColumn("ML score", min_value=0, max_value=100, format="%.1f"),
    "product_views":     st.column_config.NumberColumn("Product views"),
    "add_to_cart_count": st.column_config.NumberColumn("Add to cart"),
    "cart_abandoned":    st.column_config.TextColumn("Cart abandoned"),
    "duration":          st.column_config.TextColumn("Session duration"),
    "rules_fired":       st.column_config.TextColumn("Rules fired"),
}

st.dataframe(
    df[DISPLAY_COLS],
    use_container_width=True,
    hide_index=True,
    column_config=COLUMN_CONFIG,
)

csv_cols = [
    "session_id", "anonymous_user_id", "source", "score_tier", "rule_score", "ml_score",
    "product_views", "add_to_cart_count", "cart_abandoned", "session_duration_seconds",
    "rules_fired", "first_event_at", "last_event_at",
]
st.download_button(
    label="Download CSV",
    data=df[[c for c in csv_cols if c in df.columns]].to_csv(index=False),
    file_name="leads.csv",
    mime="text/csv",
)

# ---------------------------------------------------------------------------
# Phase 16 — Per-lead AI script generation
# ---------------------------------------------------------------------------

st.write("---")
st.subheader("AI Sales Script Generator")
st.caption(
    "Click **Generate Script** on any lead to create a personalised outreach script "
    "via OpenRouter free-tier LLM. Set OPENROUTER_API_KEY in your environment to enable."
)

_MAX_SCRIPT_ROWS = 20
script_rows = df.head(_MAX_SCRIPT_ROWS)

for _, row in script_rows.iterrows():
    uid: str = row["anonymous_user_id"]
    tier: str = row.get("score_tier", "cold")

    tier_emoji = {"hot": "🔥", "warm": "🌡️", "cold": "❄️"}.get(tier, "")
    with st.expander(
        f"{tier_emoji} {uid[:20]}  ·  {tier.upper()}  ·  rule={int(row.get('rule_score', 0))}",
        expanded=False,
    ):
        script_key = f"script_{uid}"

        if st.button("Generate Script", key=f"Generate Script##{uid}"):
            with st.spinner("Generating sales script via OpenRouter…"):
                script_text = _call_build_script(uid)
            st.session_state[script_key] = script_text

        if script_key in st.session_state:
            script_text: str = st.session_state[script_key]

            if _SENTINEL_NOT_FOUND in script_text:
                st.warning(script_text)
            elif _SENTINEL_TIMEOUT in script_text:
                st.error(script_text)
            else:
                st.text_area(
                    label="Generated Script",
                    value=script_text,
                    height=200,
                    key=f"ta_{uid}",
                )
                # Show metadata from ai_script_log
                log_entry = _fetch_last_log_entry(client, uid)
                if log_entry:
                    st.caption(
                        f"Model: `{log_entry['model']}` · "
                        f"Prompt: {log_entry['prompt_tokens']} chars · "
                        f"Response: {log_entry['output_tokens']} chars · "
                        f"Generated: {log_entry['generated_at']}"
                    )

# ---------------------------------------------------------------------------
# Phase 16 — Script History panel
# ---------------------------------------------------------------------------

st.write("---")
st.subheader("Script History")

log_df = _fetch_script_log(client)

if log_df.empty:
    st.info("No scripts generated yet — click 'Generate Script' on any lead row above.")
else:
    log_df["lead_id"] = log_df["lead_id"].str[:20]
    st.dataframe(
        log_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "lead_id":        st.column_config.TextColumn("Lead ID"),
            "tier":           st.column_config.TextColumn("Tier"),
            "model":          st.column_config.TextColumn("Model"),
            "prompt_chars":   st.column_config.NumberColumn("Prompt (chars)"),
            "response_chars": st.column_config.NumberColumn("Response (chars)"),
            "generated_at":   st.column_config.DatetimeColumn("Generated At", format="DD MMM HH:mm"),
        },
    )
