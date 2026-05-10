"""
Phase 17 — Product Input & Lead Prediction Interface.

Samples N synthetic behavioral sessions from the CTGAN model conditioned on a
product category, scores them with the LightGBM MLScorer, and presents:
  - Conversion rate metric
  - Tier distribution pie chart
  - Feature importance bar chart
  - Top-10 session table
  - Prediction history from analytics.prediction_log

Accessible at the "Predict" entry in the Streamlit sidebar navigation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Predict — Product Lead Predictor", layout="wide")

# ---------------------------------------------------------------------------
# Repo root on sys.path so src/prediction is importable
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
# Data helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_categories() -> list[str]:
    """Return top-50 category IDs ordered by event volume."""
    try:
        client = _get_client()
        result = client.query(
            """
            SELECT toString(category_id) AS cat_id
            FROM analytics.category_tree
            ORDER BY category_id
            LIMIT 200
            """
        )
        cats = [r[0] for r in result.result_rows]
        return cats if cats else ["1051", "1052", "1053"]
    except Exception:
        return ["1051", "1052", "1053"]


def _fetch_prediction_log(client) -> pd.DataFrame:
    try:
        result = client.query(
            """
            SELECT
                product_name,
                category,
                price,
                n_sessions_sampled,
                conversion_rate_pct,
                tier_hot_pct,
                tier_warm_pct,
                tier_cold_pct,
                used_conditional,
                predicted_at
            FROM analytics.prediction_log
            ORDER BY predicted_at DESC
            LIMIT 20
            """
        )
        return pd.DataFrame(result.result_rows, columns=result.column_names)
    except Exception:
        return pd.DataFrame()


def _run_prediction(category: str, price: float, keywords: str, n_sessions: int,
                    model_path: Path):
    """Lazy-import predict_for_product to avoid heavy deps at module load time."""
    from src.prediction.product_predictor import predict_for_product
    return predict_for_product(
        category=category,
        price=price,
        keywords=keywords,
        n_sessions=n_sessions,
        model_path=model_path,
    )


def _log_prediction(client, product_name: str, result, price: float, keywords: str) -> None:
    try:
        client.insert(
            "analytics.prediction_log",
            [[
                product_name,
                result.category,
                float(price),
                keywords,
                result.n_sessions_sampled,
                result.conversion_rate_pct,
                result.tier_distribution_pct.get("hot", 0.0),
                result.tier_distribution_pct.get("warm", 0.0),
                result.tier_distribution_pct.get("cold", 0.0),
                int(result.used_conditional),
            ]],
            column_names=[
                "product_name", "category", "price", "keywords",
                "n_sessions_sampled", "conversion_rate_pct",
                "tier_hot_pct", "tier_warm_pct", "tier_cold_pct",
                "used_conditional",
            ],
        )
    except Exception:
        pass  # log failure is non-fatal


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _tier_pie(tier_pct: dict[str, float]):
    import plotly.graph_objects as go
    colors = {"hot": "#ef4444", "warm": "#f97316", "cold": "#60a5fa"}
    labels = list(tier_pct.keys())
    values = list(tier_pct.values())
    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker_colors=[colors.get(l, "#94a3b8") for l in labels],
        hole=0.4,
        textinfo="label+percent",
    ))
    fig.update_layout(
        title="Lead Tier Distribution",
        showlegend=False,
        margin=dict(t=40, b=10, l=10, r=10),
        height=320,
    )
    return fig


def _feature_bar(top_features: list[dict]):
    import plotly.graph_objects as go
    names = [f["name"] for f in top_features]
    vals = [f["importance"] for f in top_features]
    fig = go.Figure(go.Bar(
        x=vals,
        y=names,
        orientation="h",
        marker_color="#6366f1",
    ))
    fig.update_layout(
        title="Top Feature Importances",
        xaxis_title="Relative importance",
        yaxis=dict(autorange="reversed"),
        margin=dict(t=40, b=10, l=10, r=10),
        height=320,
    )
    return fig


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.title("Product Lead Predictor")
st.caption(
    "Enter product details to sample synthetic behavioral sessions from the CTGAN model "
    "and estimate lead conversion likelihood."
)

categories = _fetch_categories()

# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------

with st.form("predict_form"):
    col_left, col_right = st.columns(2)

    with col_left:
        product_name = st.text_input("Product name", placeholder="e.g. Wireless Headphones")
        category = st.selectbox("Category", options=categories,
                                help="Category ID from the product taxonomy")
        price = st.number_input("Price (USD)", min_value=0.01, value=29.99, step=0.01,
                                format="%.2f")

    with col_right:
        keywords = st.text_input("Keywords (comma-separated)",
                                 placeholder="e.g. audio,bluetooth,noise-cancelling")
        n_sessions = st.slider("Synthetic sessions to sample", min_value=100,
                               max_value=5000, value=1000, step=100)
        model_path = st.text_input("CTGAN model path",
                                   value="models/ctgan_sessions.pkl",
                                   help="Relative to repo root; run 'make ctgan-train' first")

    submitted = st.form_submit_button("Run Prediction", type="primary")

# ---------------------------------------------------------------------------
# Run prediction
# ---------------------------------------------------------------------------

if submitted:
    if not product_name.strip():
        st.warning("Please enter a product name.")
        st.stop()

    _model_path = _REPO_ROOT / model_path

    with st.spinner(f"Sampling {n_sessions:,} sessions for category {category}…"):
        try:
            result = _run_prediction(
                category=category,
                price=price,
                keywords=keywords,
                n_sessions=n_sessions,
                model_path=_model_path,
            )
        except FileNotFoundError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error(f"Prediction failed: {exc}")
            st.stop()

    st.success(f"Prediction complete — {result.n_sessions_sampled:,} sessions sampled.")

    if not result.used_conditional:
        st.warning(
            f"Category **{category}** was not seen during CTGAN training. "
            "Unconditional sampling was used — results are indicative only."
        )

    # -------------------------------------------------------------------------
    # Metrics row
    # -------------------------------------------------------------------------

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Conversion rate", f"{result.conversion_rate_pct:.1f}%")
    m2.metric("🔥 Hot leads", f"{result.tier_distribution_pct.get('hot', 0):.1f}%")
    m3.metric("🌡️ Warm leads", f"{result.tier_distribution_pct.get('warm', 0):.1f}%")
    m4.metric("❄️ Cold leads", f"{result.tier_distribution_pct.get('cold', 0):.1f}%")

    # -------------------------------------------------------------------------
    # Charts
    # -------------------------------------------------------------------------

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(_tier_pie(result.tier_distribution_pct), use_container_width=True)
    with chart_right:
        if result.top_features:
            st.plotly_chart(_feature_bar(result.top_features), use_container_width=True)
        else:
            st.info("Feature importances unavailable — ML model not loaded.")

    # -------------------------------------------------------------------------
    # Top sessions table
    # -------------------------------------------------------------------------

    st.subheader("Top 10 Sessions by Score")
    display_df = result.sample_sessions.copy()
    if "ml_lead_score" in display_df.columns:
        display_df["ml_lead_score"] = display_df["ml_lead_score"].map("{:.3f}".format)
    st.dataframe(display_df, use_container_width=True)

    # -------------------------------------------------------------------------
    # Log to ClickHouse (best-effort)
    # -------------------------------------------------------------------------

    try:
        _log_prediction(_get_client(), product_name, result, price, keywords)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Prediction history
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Prediction History")

try:
    history_df = _fetch_prediction_log(_get_client())
except Exception as exc:
    st.warning(f"Could not load prediction history: {exc}")
    history_df = pd.DataFrame()

if history_df.empty:
    st.info(
        "No predictions logged yet. "
        "Apply the schema first: `make schema-phase17`, then run a prediction."
    )
else:
    st.dataframe(history_df, use_container_width=True)
