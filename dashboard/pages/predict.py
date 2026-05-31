"""
Phase 17 + 19 — Product Input & Lead Prediction Interface.

Phase 17: Streamlit form → prediction results display.
Phase 19: Calls the prediction-api REST service instead of importing
          CTGAN/LightGBM directly, keeping the dashboard process lean.

Environment variables:
    PREDICTION_API_URL   default: http://localhost:8000
                         Set to http://prediction-api:8000 in Docker Compose.

Accessible at the "Predict" entry in the Streamlit sidebar navigation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Predict — Product Lead Predictor", layout="wide")

# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------

_API_URL = os.getenv("PREDICTION_API_URL", "http://localhost:8000").rstrip("/")

# ---------------------------------------------------------------------------
# ClickHouse connection (categories only — prediction + history via API)
# ---------------------------------------------------------------------------

CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB       = os.getenv("CLICKHOUSE_DB", "analytics")
CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER", "analytics")
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
# API helpers
# ---------------------------------------------------------------------------

def _api_predict(
    product_name: str,
    category: str,
    price: float,
    keywords: str,
    n_sessions: int,
) -> dict:
    """
    POST /predict/product and return the parsed JSON response dict.
    Raises requests.HTTPError on non-2xx status.
    """
    import requests

    resp = requests.post(
        f"{_API_URL}/predict/product",
        json={
            "product_name": product_name,
            "category": category,
            "price": price,
            "keywords": keywords,
            "n_sessions": n_sessions,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _api_history(limit: int = 5) -> list[dict]:
    """GET /predictions/history and return list of prediction dicts."""
    import requests

    try:
        resp = requests.get(
            f"{_API_URL}/predictions/history",
            params={"limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def _api_health() -> dict | None:
    """GET /health — returns None if the API is unreachable."""
    import requests

    try:
        resp = requests.get(f"{_API_URL}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Category list — real Retailrocket category IDs, ranked by session popularity
# ---------------------------------------------------------------------------
#
# Retailrocket's categories are anonymized integer IDs with no public label
# dictionary, so we expose them as "Category <id> (<n> sessions)" ordered by
# how often each was the modal product-view category in a real session. These
# are exactly the IDs the CTGAN was trained on, so picking any of them
# triggers the conditional-sampling path instead of the unconditional fallback.

_TOP_CATEGORIES_LIMIT = 50


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_categories() -> dict[str, str]:
    """Return {label: category_id} dict — top retailrocket categories by sessions."""
    try:
        result = _get_client().query(
            f"""
            SELECT category_id, count() AS sessions
            FROM (
                SELECT
                    topK(1)(toString(il.category_id))[1] AS category_id
                FROM analytics.unified_events AS ue
                INNER JOIN retailrocket_raw.item_latest AS il
                    ON toUInt64OrZero(ue.product_id) = il.item_id
                WHERE ue.source = 'retailrocket'
                  AND ue.event_type = 'product_view'
                  AND il.category_id IS NOT NULL
                GROUP BY ue.session_id
            )
            GROUP BY category_id
            ORDER BY sessions DESC
            LIMIT {_TOP_CATEGORIES_LIMIT}
            """
        )
        merged: dict[str, str] = {}
        for cat_id, sessions in result.result_rows:
            label = f"Category {cat_id} ({sessions:,} sessions)"
            merged[label] = str(cat_id)
        if merged:
            return merged
    except Exception:
        pass

    # Fallback if the retailrocket_raw tables aren't reachable — synthesize a
    # minimal list from known popular IDs so the dropdown is never empty.
    return {f"Category {cid}": cid for cid in ("1051", "1483", "491", "959", "342")}


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _tier_pie(tier_pct: dict):
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
    vals  = [f["importance"] for f in top_features]
    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h", marker_color="#6366f1",
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
# Page header + API status banner
# ---------------------------------------------------------------------------

st.title("Product Lead Predictor")
st.caption(
    "Enter product details to sample synthetic behavioral sessions from the CTGAN model "
    "and estimate lead conversion likelihood. Predictions are served by the ML API service."
)

health = _api_health()
if health is None:
    st.warning(
        f"Prediction API unreachable at **{_API_URL}**. "
        "Run `make api-up` to start it, or set `PREDICTION_API_URL` to the correct address. "
        "The form is disabled until the API responds."
    )
    _api_ready = False
else:
    ch_icon = "✅" if health.get("clickhouse") == "ok" else "⚠️"
    st.sidebar.success(
        f"API online — model: `{health.get('active_model', '?')}` {ch_icon} ClickHouse"
    )
    _api_ready = True

# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------

category_map = _fetch_categories()   # {label: id}
category_labels = list(category_map.keys())

with st.form("predict_form"):
    col_left, col_right = st.columns(2)

    with col_left:
        product_name = st.text_input("Product name",
                                     placeholder="e.g. Wireless Headphones",
                                     disabled=not _api_ready)
        selected_label = st.selectbox("Category", options=category_labels,
                                      help="Product category for behavioral sampling",
                                      disabled=not _api_ready)
        category = category_map.get(selected_label, selected_label)
        price = st.number_input("Price (USD)", min_value=0.01, value=29.99,
                                step=0.01, format="%.2f", disabled=not _api_ready)

    with col_right:
        keywords = st.text_input("Keywords (comma-separated)",
                                 placeholder="e.g. audio,bluetooth,noise-cancelling",
                                 disabled=not _api_ready)
        n_sessions = st.slider("Synthetic sessions to sample", min_value=100,
                               max_value=5000, value=1000, step=100,
                               disabled=not _api_ready)

    submitted = st.form_submit_button(
        "Run Prediction", type="primary", disabled=not _api_ready
    )

# ---------------------------------------------------------------------------
# Run prediction via API
# ---------------------------------------------------------------------------

if submitted:
    if not product_name.strip():
        st.warning("Please enter a product name.")
        st.stop()

    with st.spinner(f"Generating predictions via ML service ({n_sessions:,} sessions)…"):
        try:
            data = _api_predict(
                product_name=product_name,
                category=category,
                price=price,
                keywords=keywords,
                n_sessions=n_sessions,
            )
        except Exception as exc:
            error_msg = str(exc)
            try:
                import requests
                if hasattr(exc, "response") and exc.response is not None:
                    detail = exc.response.json().get("detail", error_msg)
                    error_msg = detail
            except Exception:
                pass
            st.error(f"Prediction API error: {error_msg}")
            st.stop()

    st.success(
        f"Prediction complete — {data['n_sessions_sampled']:,} sessions sampled "
        f"(model: `{data.get('model_version', '?')}`)."
    )

    if not data.get("used_conditional_sampling", True):
        st.warning(
            f"Category **{category}** was not seen during CTGAN training. "
            "Unconditional sampling was used — results are indicative only."
        )

    # -------------------------------------------------------------------------
    # Metrics row
    # -------------------------------------------------------------------------

    tier_pct = data.get("tier_distribution_pct", {})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Conversion rate", f"{data['conversion_rate_pct']:.1f}%")
    m2.metric("🔥 Hot leads",  f"{tier_pct.get('hot',  0):.1f}%")
    m3.metric("🌡️ Warm leads", f"{tier_pct.get('warm', 0):.1f}%")
    m4.metric("❄️ Cold leads", f"{tier_pct.get('cold', 0):.1f}%")

    # -------------------------------------------------------------------------
    # Charts
    # -------------------------------------------------------------------------

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(_tier_pie(tier_pct), use_container_width=True)
    with chart_right:
        top_features = data.get("top_features", [])
        if top_features:
            st.plotly_chart(_feature_bar(top_features), use_container_width=True)
        else:
            st.info("Feature importances unavailable.")

    # -------------------------------------------------------------------------
    # Top sessions table
    # -------------------------------------------------------------------------

    st.subheader("Top 10 Sessions by Score")
    sessions = data.get("sample_sessions", [])
    if sessions:
        display_df = pd.DataFrame(sessions)
        if "ml_lead_score" in display_df.columns:
            display_df["ml_lead_score"] = display_df["ml_lead_score"].map("{:.3f}".format)
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No session data returned.")

    st.caption(
        "Disclaimer: predictions are estimates over synthetic data — not guaranteed outcomes."
    )

# ---------------------------------------------------------------------------
# Prediction History expander (via API)
# ---------------------------------------------------------------------------

st.divider()

with st.expander("Prediction History (last 5)", expanded=False):
    history = _api_history(limit=5)
    if history:
        hist_df = pd.DataFrame(history)
        if "predicted_at" in hist_df.columns:
            hist_df["predicted_at"] = pd.to_datetime(hist_df["predicted_at"]).dt.strftime(
                "%Y-%m-%d %H:%M"
            )
        st.dataframe(hist_df, use_container_width=True)
    else:
        st.info(
            "No predictions logged yet, or the API is unreachable. "
            "Run a prediction above to populate this panel."
        )
