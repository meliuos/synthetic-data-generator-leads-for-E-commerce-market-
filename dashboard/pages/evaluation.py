"""
Evaluation & Testing Dashboard — Model Quality, LLM Metrics, Drift, System Health.

Provides a unified view of all measurable system quality signals:
  - ML model: score distributions, tier breakdown, rule vs ML agreement
  - Rule engine: per-rule trigger rates
  - LLM inference: latency, token counts, tier distribution, cost tracking
  - Data drift: per-feature Jensen-Shannon divergence, historical drift log
  - System health: ClickHouse, Prediction API, OpenRouter connectivity

Accessible at the "Evaluation" entry in the Streamlit sidebar navigation.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Evaluation — Lead Intelligence", layout="wide")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.scoring.ml_scorer import MLScorer
from src.scoring.rules import SessionFeatures, score_session

# ---------------------------------------------------------------------------
# ClickHouse connection
# ---------------------------------------------------------------------------

CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB       = os.getenv("CLICKHOUSE_DB", "analytics")
CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER", "analytics")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "analytics_password")
PREDICTION_API_URL  = os.getenv("PREDICTION_API_URL", "http://localhost:8000").rstrip("/")


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


def _query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a ClickHouse query and return a DataFrame. Returns empty DF on error."""
    try:
        client = _get_client()
        result = client.query(sql, parameters=params or {})
        return pd.DataFrame(result.result_rows, columns=result.column_names)
    except Exception as exc:
        st.warning(f"Query failed: {exc}")
        return pd.DataFrame()


@st.cache_resource(show_spinner=False)
def _get_ml_scorer() -> MLScorer | None:
    try:
        return MLScorer()
    except Exception as exc:
        st.warning(f"ML scorer unavailable: {exc}")
        return None


def _build_session_features(prefix: str) -> SessionFeatures:
    return SessionFeatures(
        session_id=st.session_state[f"{prefix}_session_id"].strip() or "demo-session",
        anonymous_user_id=st.session_state[f"{prefix}_anonymous_user_id"].strip() or "demo-user",
        page_views=int(st.session_state[f"{prefix}_page_views"]),
        product_views=int(st.session_state[f"{prefix}_product_views"]),
        add_to_cart_count=int(st.session_state[f"{prefix}_add_to_cart_count"]),
        purchase_count=int(st.session_state[f"{prefix}_purchase_count"]),
        search_count=int(st.session_state[f"{prefix}_search_count"]),
        max_scroll_pct=(
            float(st.session_state[f"{prefix}_max_scroll_pct"])
            if st.session_state[f"{prefix}_has_scroll_pct"]
            else None
        ),
        session_duration_seconds=int(st.session_state[f"{prefix}_session_duration_seconds"]),
        distinct_products_viewed=int(st.session_state[f"{prefix}_distinct_products_viewed"]),
        cart_abandoned=int(st.session_state[f"{prefix}_cart_abandoned"]),
        source=st.session_state[f"{prefix}_source"],
    )


def _render_scoring_test_form(prefix: str, title: str) -> bool:
    st.markdown(f"### {title}")
    with st.form(f"{prefix}_lead_scoring_test_form"):
        col_left, col_right = st.columns(2)

        with col_left:
            st.text_input("Session ID", value="demo-session", key=f"{prefix}_session_id")
            st.text_input("Anonymous user ID", value="demo-user", key=f"{prefix}_anonymous_user_id")
            st.selectbox("Source", options=["live", "retailrocket"], key=f"{prefix}_source")
            st.number_input("Page views", min_value=0, value=1, step=1, key=f"{prefix}_page_views")
            st.number_input("Product views", min_value=0, value=2, step=1, key=f"{prefix}_product_views")
            st.number_input("Add to cart", min_value=0, value=1, step=1, key=f"{prefix}_add_to_cart_count")
            st.number_input("Purchases", min_value=0, value=0, step=1, key=f"{prefix}_purchase_count")

        with col_right:
            st.number_input("Searches", min_value=0, value=1, step=1, key=f"{prefix}_search_count")
            st.number_input(
                "Distinct products viewed",
                min_value=0,
                value=3,
                step=1,
                key=f"{prefix}_distinct_products_viewed",
            )
            st.number_input(
                "Session duration (seconds)",
                min_value=0,
                value=180,
                step=10,
                key=f"{prefix}_session_duration_seconds",
            )
            st.checkbox("Scroll data available", value=True, key=f"{prefix}_has_scroll_pct")
            if st.session_state[f"{prefix}_has_scroll_pct"]:
                st.number_input(
                    "Max scroll pct",
                    min_value=0.0,
                    max_value=100.0,
                    value=75.0,
                    step=1.0,
                    format="%.1f",
                    key=f"{prefix}_max_scroll_pct",
                )
            else:
                st.number_input(
                    "Max scroll pct",
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                    step=1.0,
                    format="%.1f",
                    key=f"{prefix}_max_scroll_pct",
                    disabled=True,
                )
            st.selectbox(
                "Cart abandoned",
                options=[0, 1],
                format_func=lambda value: "Yes" if value == 1 else "No",
                key=f"{prefix}_cart_abandoned",
            )

        return st.form_submit_button("Run Lead Score Test", type="primary")


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("Evaluation & Testing")
st.caption(
    "Quality metrics for the ML model, rule engine, LLM inference, synthetic data, "
    "and live system health. All data sourced from ClickHouse analytics tables."
)

tab_ml, tab_rules, tab_llm, tab_drift, tab_health = st.tabs([
    "ML Model",
    "Rule Engine",
    "LLM Scripts",
    "Data Drift",
    "System Health",
])

# ===========================================================================
# TAB 1 — ML Model
# ===========================================================================

with tab_ml:
    st.subheader("ML Model — Score Distributions")

    ml_test_submitted = _render_scoring_test_form("ml", "Lead Scoring Test — ML Model")
    if ml_test_submitted:
        features = _build_session_features("ml")
        scorer = _get_ml_scorer()
        if scorer is None:
            st.error("ML scorer is unavailable. Check that the trained model and ML dependencies are installed.")
        else:
            score_input = pd.DataFrame([
                {
                    "product_views": features.product_views,
                    "add_to_cart_count": features.add_to_cart_count,
                    "distinct_products_viewed": features.distinct_products_viewed,
                    "max_scroll_pct": features.max_scroll_pct,
                    "search_count": features.search_count,
                    "session_duration_seconds": features.session_duration_seconds,
                }
            ])
            ml_score = float(scorer.predict(score_input).iloc[0] * 100)
            ml_tier = scorer.score_tier(pd.Series([ml_score])).iloc[0]

            c1, c2, c3 = st.columns(3)
            c1.metric("ML score", f"{ml_score:.1f}")
            c2.metric("Tier", ml_tier.title())
            c3.metric("Source", features.source)

            st.caption(
                "ML scoring uses the active LightGBM model and the same six feature columns as the batch pipeline."
            )
            st.dataframe(
                pd.DataFrame([
                    {
                        "session_id": features.session_id,
                        "anonymous_user_id": features.anonymous_user_id,
                        "product_views": features.product_views,
                        "add_to_cart_count": features.add_to_cart_count,
                        "distinct_products_viewed": features.distinct_products_viewed,
                        "max_scroll_pct": features.max_scroll_pct,
                        "search_count": features.search_count,
                        "session_duration_seconds": features.session_duration_seconds,
                    }
                ]),
                use_container_width=True,
                hide_index=True,
            )

    # --- summary metrics ----------------------------------------------------
    # score_tier is derived — the ML table only stores ml_lead_score (0–1 float)
    counts_df = _query("""
        SELECT
            multiIf(ml_lead_score >= 0.60, 'hot',
                    ml_lead_score >= 0.30, 'warm', 'cold') AS score_tier,
            count()                      AS total,
            round(avg(ml_lead_score), 4) AS avg_score,
            round(min(ml_lead_score), 4) AS min_score,
            round(max(ml_lead_score), 4) AS max_score
        FROM analytics.lead_scores_ml FINAL
        GROUP BY score_tier
        ORDER BY avg_score DESC
    """)

    total_df = _query("SELECT count() AS n FROM analytics.lead_scores_ml FINAL")
    total_n = int(total_df.iloc[0]["n"]) if not total_df.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total scored sessions", f"{total_n:,}")
    if not counts_df.empty:
        tier_totals = counts_df.set_index("score_tier")["total"]
        col2.metric("Hot leads",  int(tier_totals.get("hot",  0)))
        col3.metric("Warm leads", int(tier_totals.get("warm", 0)))
        col4.metric("Cold leads", int(tier_totals.get("cold", 0)))

    if counts_df.empty:
        st.info("No ML scores yet — run `make score-sessions` to populate analytics.lead_scores_ml.")
    else:
        # --- tier pie chart -------------------------------------------------
        chart_left, chart_right = st.columns(2)
        with chart_left:
            fig_pie = px.pie(
                counts_df,
                names="score_tier",
                values="total",
                color="score_tier",
                color_discrete_map={"hot": "#ef4444", "warm": "#f97316", "cold": "#60a5fa"},
                hole=0.4,
                title="Lead Tier Distribution",
            )
            fig_pie.update_layout(showlegend=False, margin=dict(t=40, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig_pie, use_container_width=True)

        with chart_right:
            st.write("**Score stats by tier**")
            display_df = counts_df.rename(columns={
                "score_tier": "Tier", "total": "Count",
                "avg_score": "Avg Score", "min_score": "Min", "max_score": "Max",
            })
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- score histogram ----------------------------------------------------
    st.write("---")
    st.subheader("Score Histogram")
    hist_df = _query("""
        SELECT
            multiIf(ml_lead_score >= 0.60, 'hot',
                    ml_lead_score >= 0.30, 'warm', 'cold') AS score_tier,
            round(ml_lead_score * 100, 0) AS score_pct
        FROM analytics.lead_scores_ml FINAL
        LIMIT 50000
    """)

    if not hist_df.empty:
        fig_hist = px.histogram(
            hist_df,
            x="score_pct",
            color="score_tier",
            barmode="overlay",
            nbins=50,
            color_discrete_map={"hot": "#ef4444", "warm": "#f97316", "cold": "#60a5fa"},
            labels={"score_pct": "ML Score (0–100)", "score_tier": "Tier"},
            title="ML Score Distribution by Tier",
            opacity=0.75,
        )
        fig_hist.update_layout(margin=dict(t=40, b=10), height=350)
        st.plotly_chart(fig_hist, use_container_width=True)

    # --- model version info -------------------------------------------------
    st.write("---")
    st.subheader("Active Model Version")
    try:
        import requests
        health_resp = requests.get(f"{PREDICTION_API_URL}/health", timeout=5)
        if health_resp.status_code == 200:
            h = health_resp.json()
            st.json({
                "active_model": h.get("active_model", "unknown"),
                "clickhouse": h.get("clickhouse", "unknown"),
                "api_status": "ok",
            })
        else:
            st.warning("Prediction API returned non-200. Check `make api-up`.")
    except Exception as exc:
        st.info(f"Prediction API unreachable ({exc}). Active model info unavailable.")

    # --- ML vs rule tier agreement ------------------------------------------
    st.write("---")
    st.subheader("ML vs Rule Tier Agreement")
    agree_df = _query("""
        SELECT
            multiIf(ml.ml_lead_score >= 0.60, 'hot',
                    ml.ml_lead_score >= 0.30, 'warm', 'cold') AS ml_tier,
            r.score_tier      AS rule_tier,
            count()           AS n
        FROM analytics.lead_scores_ml AS ml FINAL
        INNER JOIN analytics.lead_scores_rule_based AS r FINAL
            ON ml.anonymous_user_id = r.anonymous_user_id
        GROUP BY ml_tier, rule_tier
        ORDER BY n DESC
        LIMIT 20
    """)

    if not agree_df.empty:
        agree_df["agree"] = agree_df["ml_tier"] == agree_df["rule_tier"]
        total_agree = agree_df.loc[agree_df["agree"], "n"].sum()
        total_all   = agree_df["n"].sum()
        rate = 100 * total_agree / total_all if total_all > 0 else 0
        st.metric("Tier agreement rate (ML == Rule)", f"{rate:.1f}%",
                  help="Percentage of sessions where ML tier matches rule-based tier.")
        fig_agree = px.bar(
            agree_df,
            x="rule_tier", y="n", color="ml_tier",
            barmode="group",
            color_discrete_map={"hot": "#ef4444", "warm": "#f97316", "cold": "#60a5fa"},
            labels={"rule_tier": "Rule Tier", "n": "Sessions", "ml_tier": "ML Tier"},
            title="ML vs Rule Tier Cross-Tab",
        )
        fig_agree.update_layout(height=320, margin=dict(t=40, b=10))
        st.plotly_chart(fig_agree, use_container_width=True)
    else:
        st.info("Insufficient data for ML vs Rule agreement — both scoring pipelines must be populated.")

# ===========================================================================
# TAB 2 — Rule Engine
# ===========================================================================

with tab_rules:
    st.subheader("Rule Engine — Trigger Rates")

    rule_test_submitted = _render_scoring_test_form("rule", "Lead Scoring Test — Rule Engine")
    if rule_test_submitted:
        features = _build_session_features("rule")
        result = score_session(features)

        c1, c2, c3 = st.columns(3)
        c1.metric("Rule score", f"{result.lead_score}")
        c2.metric("Tier", result.score_tier.title())
        c3.metric("Source", result.source)

        fired_rules = list(result.rule_contributions.items())
        if fired_rules:
            st.write("**Fired rules**")
            st.dataframe(
                pd.DataFrame(
                    [{"Rule": name, "Delta": delta} for name, delta in fired_rules]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No rule fired for this session; the score stayed at the baseline.")

        st.caption("Rule scoring uses the deterministic Phase 10 engine with the same thresholds as the ClickHouse view.")

    rule_cols = [
        "rule_add_to_cart",
        "rule_purchase",
        "rule_browsing_depth",
        "rule_search_intent",
        "rule_scroll_engagement",
        "rule_bouncer",
    ]
    rule_labels = {
        "rule_add_to_cart":       "Add to Cart",
        "rule_purchase":          "Purchase",
        "rule_browsing_depth":    "Deep Browse",
        "rule_search_intent":     "Search Intent",
        "rule_scroll_engagement": "Scroll 70%+",
        "rule_bouncer":           "Bouncer",
    }

    sum_exprs = ", ".join(f"sum({c}) AS {c}" for c in rule_cols)
    trigger_df = _query(f"""
        SELECT
            count()          AS total_sessions,
            {sum_exprs}
        FROM analytics.lead_scores_rule_based FINAL
    """)

    if trigger_df.empty or int(trigger_df.iloc[0]["total_sessions"]) == 0:
        st.info("No rule scores yet — run `make score-sessions` to populate analytics.lead_scores_rule_based.")
    else:
        row = trigger_df.iloc[0]
        total = int(row["total_sessions"])
        st.metric("Total rule-scored sessions", f"{total:,}")

        # build trigger rate bar chart
        rates = []
        for col, label in rule_labels.items():
            triggered = int(row[col])
            rates.append({
                "Rule": label,
                "Sessions triggered": triggered,
                "Rate (%)": round(100 * triggered / total, 1) if total else 0,
            })
        rates_df = pd.DataFrame(rates).sort_values("Rate (%)", ascending=True)

        col_chart, col_table = st.columns([2, 1])
        with col_chart:
            fig_rules = px.bar(
                rates_df,
                x="Rate (%)", y="Rule", orientation="h",
                color="Rate (%)",
                color_continuous_scale="Blues",
                title="Rule Trigger Rate (%)",
                text="Rate (%)",
            )
            fig_rules.update_traces(texttemplate="%{text}%", textposition="outside")
            fig_rules.update_layout(
                coloraxis_showscale=False,
                height=350,
                margin=dict(t=40, b=10, r=60),
            )
            st.plotly_chart(fig_rules, use_container_width=True)

        with col_table:
            st.write("**Trigger counts**")
            st.dataframe(
                rates_df[["Rule", "Sessions triggered", "Rate (%)"]].sort_values(
                    "Sessions triggered", ascending=False
                ),
                use_container_width=True, hide_index=True,
            )

    # --- rule score distribution -------------------------------------------
    st.write("---")
    st.subheader("Rule Score Distribution")
    rule_hist_df = _query("""
        SELECT
            lead_score  AS rule_score,
            score_tier
        FROM analytics.lead_scores_rule_based FINAL
        LIMIT 50000
    """)

    if not rule_hist_df.empty:
        fig_rhist = px.histogram(
            rule_hist_df, x="rule_score", color="score_tier",
            barmode="stack", nbins=30,
            color_discrete_map={"hot": "#ef4444", "warm": "#f97316", "cold": "#60a5fa"},
            labels={"rule_score": "Rule Score", "score_tier": "Tier"},
            title="Rule Score Distribution",
            opacity=0.85,
        )
        fig_rhist.update_layout(height=320, margin=dict(t=40, b=10))
        st.plotly_chart(fig_rhist, use_container_width=True)

    # --- co-occurring rule patterns -----------------------------------------
    st.write("---")
    st.subheader("Top Rule Combinations (hot leads)")
    hot_rules_df = _query("""
        SELECT
            rule_add_to_cart, rule_purchase, rule_browsing_depth,
            rule_search_intent, rule_scroll_engagement, rule_bouncer,
            count() AS n
        FROM analytics.lead_scores_rule_based FINAL
        WHERE score_tier = 'hot'
        GROUP BY
            rule_add_to_cart, rule_purchase, rule_browsing_depth,
            rule_search_intent, rule_scroll_engagement, rule_bouncer
        ORDER BY n DESC
        LIMIT 10
    """)

    if not hot_rules_df.empty:
        def _combo_label(row):
            fired = []
            mapping = {
                "rule_add_to_cart": "cart", "rule_purchase": "purchase",
                "rule_browsing_depth": "browse", "rule_search_intent": "search",
                "rule_scroll_engagement": "scroll", "rule_bouncer": "bounce",
            }
            for col, lbl in mapping.items():
                if row.get(col, 0) == 1:
                    fired.append(lbl)
            return " + ".join(fired) if fired else "none"

        hot_rules_df["combination"] = hot_rules_df.apply(_combo_label, axis=1)
        st.dataframe(
            hot_rules_df[["combination", "n"]].rename(columns={"combination": "Rules fired", "n": "Hot sessions"}),
            use_container_width=True, hide_index=True,
        )

# ===========================================================================
# TAB 3 — LLM Scripts
# ===========================================================================

with tab_llm:
    st.subheader("LLM Script Generation — Performance Metrics")

    llm_summary_df = _query("""
        SELECT
            count()                       AS total_scripts,
            round(avg(output_tokens), 0)  AS avg_response_chars,
            round(avg(prompt_tokens), 0)  AS avg_prompt_chars,
            round(sum(cost_usd), 4)       AS total_cost_usd
        FROM analytics.ai_script_log
    """)

    if llm_summary_df.empty or int(llm_summary_df.iloc[0]["total_scripts"]) == 0:
        st.info(
            "No scripts generated yet. "
            "Go to the **Leads** page, select a lead, and click **Generate Script**."
        )
    else:
        s = llm_summary_df.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total scripts generated",  int(s["total_scripts"]))
        c2.metric("Avg prompt (chars)",        int(s["avg_prompt_chars"]))
        c3.metric("Avg response (chars)",      int(s["avg_response_chars"]))
        c4.metric("Total cost (USD)",          f"${float(s['total_cost_usd']):.4f}",
                  help="Always $0 for free-tier OpenRouter models.")

    # --- by tier breakdown --------------------------------------------------
    tier_llm_df = _query("""
        SELECT
            tier,
            count()                      AS scripts,
            round(avg(prompt_tokens), 0) AS avg_prompt,
            round(avg(output_tokens), 0) AS avg_response
        FROM analytics.ai_script_log
        GROUP BY tier
        ORDER BY scripts DESC
    """)

    if not tier_llm_df.empty:
        chart_l, chart_r = st.columns(2)
        with chart_l:
            fig_tier = px.bar(
                tier_llm_df, x="tier", y="scripts",
                color="tier",
                color_discrete_map={"hot": "#ef4444", "warm": "#f97316", "cold": "#60a5fa"},
                title="Scripts Generated by Tier",
                text="scripts",
            )
            fig_tier.update_traces(textposition="outside")
            fig_tier.update_layout(showlegend=False, height=300, margin=dict(t=40, b=10))
            st.plotly_chart(fig_tier, use_container_width=True)

        with chart_r:
            fig_chars = px.bar(
                tier_llm_df,
                x="tier", y=["avg_prompt", "avg_response"],
                barmode="group",
                labels={"value": "Avg chars", "variable": "Type", "tier": "Tier"},
                title="Avg Prompt vs Response Length by Tier",
                color_discrete_map={"avg_prompt": "#6366f1", "avg_response": "#10b981"},
            )
            fig_chars.update_layout(height=300, margin=dict(t=40, b=10))
            st.plotly_chart(fig_chars, use_container_width=True)

    # --- model breakdown ----------------------------------------------------
    st.write("---")
    model_df = _query("""
        SELECT model, count() AS n
        FROM analytics.ai_script_log
        GROUP BY model ORDER BY n DESC
    """)

    if not model_df.empty:
        st.write("**Models used**")
        st.dataframe(
            model_df.rename(columns={"model": "Model", "n": "Scripts"}),
            use_container_width=True, hide_index=True,
        )

    # --- recent log ---------------------------------------------------------
    st.write("---")
    st.subheader("Recent Script Log")
    log_df = _query("""
        SELECT
            lead_id,
            tier,
            model,
            prompt_tokens   AS prompt_chars,
            output_tokens   AS response_chars,
            cost_usd,
            generated_at
        FROM analytics.ai_script_log
        ORDER BY generated_at DESC
        LIMIT 20
    """)

    if not log_df.empty:
        log_df["lead_id"] = log_df["lead_id"].str[:24]
        st.dataframe(
            log_df,
            use_container_width=True, hide_index=True,
            column_config={
                "lead_id":        st.column_config.TextColumn("Lead ID"),
                "tier":           st.column_config.TextColumn("Tier"),
                "model":          st.column_config.TextColumn("Model"),
                "prompt_chars":   st.column_config.NumberColumn("Prompt (chars)"),
                "response_chars": st.column_config.NumberColumn("Response (chars)"),
                "cost_usd":       st.column_config.NumberColumn("Cost (USD)", format="$%.4f"),
                "generated_at":   st.column_config.DatetimeColumn("Generated At", format="DD MMM HH:mm:ss"),
            },
        )
    else:
        st.info("No log entries yet.")

    # --- OpenRouter model reference -----------------------------------------
    st.write("---")
    with st.expander("Available free models on OpenRouter"):
        st.markdown("""
| Model ID | Notes |
|---|---|
| `meta-llama/llama-3.3-70b-instruct:free` | Default — 70B, strong quality |
| `meta-llama/llama-3.2-3b-instruct:free` | Smallest / fastest |
| `google/gemma-4-27b-it:free` | Google Gemma 27B |
| `nvidia/nemotron-3-super-120b-a12b:free` | 120B — highest quality free option |
| `deepseek/deepseek-v4-flash:free` | DeepSeek V4 Flash |
| `qwen/qwen3-coder:free` | Qwen3 Coder |

Set `LLM_MODEL=<model-id>` in your `.env` to switch models. List verified May 2026.
""")

# ===========================================================================
# TAB 4 — Data Drift
# ===========================================================================

with tab_drift:
    st.subheader("Synthetic Data Drift — Jensen-Shannon Divergence")
    st.caption(
        "JSD measures how much the synthetic session distribution has drifted from real sessions. "
        "JSD < 0.10 = OK, 0.10–0.15 = warn, > 0.15 = fail."
    )

    # --- run drift check on demand -----------------------------------------
    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        run_drift = st.button("Run Drift Check Now", type="primary")

    if run_drift:
        with st.spinner("Computing Jensen-Shannon divergence across all features…"):
            try:
                _drift_client = _get_client()
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from drift_panel import run_drift_check
                report = run_drift_check(_drift_client)
                st.session_state["eval_drift_report"] = report
            except Exception as exc:
                st.error(f"Drift check failed: {exc}")

    report = st.session_state.get("eval_drift_report")
    if report:
        status = report["status"]
        badge  = {"ok": "🟢 OK", "warn": "🟡 WARN", "fail": "🔴 FAIL"}.get(status, status)
        st.markdown(f"**Status:** {badge} &nbsp; **Max JSD:** `{report['max_jsd']}` &nbsp; **Checked:** {report['checked_at']}")

        jsd_data = report.get("all_feature_jsd", {})
        if jsd_data:
            jsd_df = pd.DataFrame(
                {"Feature": list(jsd_data.keys()), "JSD": list(jsd_data.values())}
            ).sort_values("JSD", ascending=True)

            # colour thresholds
            jsd_df["Status"] = jsd_df["JSD"].apply(
                lambda v: "fail" if v > 0.15 else ("warn" if v >= 0.10 else "ok")
            )
            color_map = {"ok": "#22c55e", "warn": "#f59e0b", "fail": "#ef4444"}

            fig_jsd = go.Figure(go.Bar(
                x=jsd_df["JSD"],
                y=jsd_df["Feature"],
                orientation="h",
                marker_color=[color_map[s] for s in jsd_df["Status"]],
                text=[f"{v:.4f}" for v in jsd_df["JSD"]],
                textposition="outside",
            ))
            fig_jsd.add_vline(x=0.10, line_dash="dash", line_color="#f59e0b", annotation_text="warn 0.10")
            fig_jsd.add_vline(x=0.15, line_dash="dash", line_color="#ef4444", annotation_text="fail 0.15")
            fig_jsd.update_layout(
                title="Per-Feature Jensen-Shannon Divergence",
                xaxis_title="JSD (lower is better)",
                height=380,
                margin=dict(t=40, b=10, r=80),
            )
            st.plotly_chart(fig_jsd, use_container_width=True)

    # --- historical drift log -----------------------------------------------
    st.write("---")
    st.subheader("Drift Check History")
    drift_hist_df = _query("""
        SELECT
            checked_at,
            features_drifted,
            max_jsd,
            status
        FROM analytics.drift_log
        ORDER BY checked_at DESC
        LIMIT 50
    """)

    if not drift_hist_df.empty:
        drift_hist_df["status_icon"] = drift_hist_df["status"].map(
            {"ok": "🟢", "warn": "🟡", "fail": "🔴"}
        ).fillna("❓")
        st.dataframe(
            drift_hist_df[["status_icon", "checked_at", "features_drifted", "max_jsd", "status"]],
            use_container_width=True, hide_index=True,
            column_config={
                "status_icon":      st.column_config.TextColumn(""),
                "checked_at":       st.column_config.DatetimeColumn("Checked At", format="DD MMM HH:mm"),
                "features_drifted": st.column_config.NumberColumn("Features drifted"),
                "max_jsd":          st.column_config.NumberColumn("Max JSD", format="%.4f"),
                "status":           st.column_config.TextColumn("Status"),
            },
        )

        # trend line
        fig_trend = px.line(
            drift_hist_df.sort_values("checked_at"),
            x="checked_at", y="max_jsd",
            markers=True,
            title="Max JSD Over Time",
            labels={"checked_at": "Time", "max_jsd": "Max JSD"},
        )
        fig_trend.add_hline(y=0.10, line_dash="dash", line_color="#f59e0b", annotation_text="warn")
        fig_trend.add_hline(y=0.15, line_dash="dash", line_color="#ef4444", annotation_text="fail")
        fig_trend.update_layout(height=300, margin=dict(t=40, b=10))
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No drift checks logged yet — click **Run Drift Check Now** above to create the first entry.")

# ===========================================================================
# TAB 5 — System Health
# ===========================================================================

with tab_health:
    st.subheader("System Health Checks")

    if st.button("Refresh All Checks", type="primary"):
        st.rerun()

    # --- ClickHouse ---------------------------------------------------------
    st.write("#### ClickHouse")
    try:
        client = _get_client()
        ping_df = pd.DataFrame(client.query("SELECT 1 AS ok").result_rows, columns=["ok"])
        st.success(f"ClickHouse is reachable at `{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}`")

        # table row counts
        tables = [
            "analytics.session_features",
            "analytics.lead_scores_rule_based",
            "analytics.lead_scores_ml",
            "analytics.ai_script_log",
            "analytics.drift_log",
            "analytics.synthetic_sessions",
        ]
        counts = []
        for t in tables:
            try:
                r = client.query(f"SELECT count() AS n FROM {t}")
                counts.append({"Table": t, "Rows": int(r.result_rows[0][0]), "Status": "ok"})
            except Exception as exc:
                counts.append({"Table": t, "Rows": None, "Status": str(exc)[:60]})
        counts_df = pd.DataFrame(counts)
        st.dataframe(counts_df, use_container_width=True, hide_index=True,
                     column_config={
                         "Table":  st.column_config.TextColumn("Table"),
                         "Rows":   st.column_config.NumberColumn("Row count", format="%d"),
                         "Status": st.column_config.TextColumn("Status"),
                     })
    except Exception as exc:
        st.error(f"ClickHouse unreachable: {exc}")

    st.write("---")

    # --- Prediction API -----------------------------------------------------
    st.write("#### Prediction API")
    try:
        import requests as _req
        resp = _req.get(f"{PREDICTION_API_URL}/health", timeout=5)
        if resp.status_code == 200:
            h = resp.json()
            st.success(f"Prediction API online at `{PREDICTION_API_URL}`")
            st.json({
                "active_model": h.get("active_model"),
                "clickhouse":   h.get("clickhouse"),
            })
        else:
            st.warning(f"Prediction API returned HTTP {resp.status_code}")
    except Exception as exc:
        st.error(f"Prediction API unreachable: {exc}. Run `make api-up`.")

    st.write("---")

    # --- OpenRouter ---------------------------------------------------------
    st.write("#### OpenRouter LLM")
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from src.ai.llm_client import check_openrouter_health, _LLM_MODEL as _active_model
        health = check_openrouter_health()

        if health["status"] == "ok":
            model_ok = health.get("model_ready", False)
            icon = "✅" if model_ok else "⚠️"
            st.success(
                f"OpenRouter reachable — {health.get('available_count', '?')} models listed."
            )
            st.json({
                "active_model":  _active_model,
                "model_ready":   model_ok,
                "available_count": health.get("available_count"),
            })
            if not model_ok:
                st.warning(
                    f"Model `{_active_model}` not found in the OpenRouter model list. "
                    "It may still be callable — try generating a script from the Leads page."
                )
        else:
            st.error(f"OpenRouter error: {health.get('error')}")
            if "OPENROUTER_API_KEY" in health.get("error", ""):
                st.info(
                    "Set `OPENROUTER_API_KEY` in your environment. "
                    "Get a free key at https://openrouter.ai/keys"
                )
    except Exception as exc:
        st.error(f"OpenRouter check failed: {exc}")

    st.write("---")

    # --- Screenshot service -------------------------------------------------
    st.write("#### Screenshot Service")
    SCREENSHOT_URL = os.getenv("SCREENSHOT_SERVICE_URL", "http://localhost:8100")
    try:
        import requests as _req
        resp = _req.get(f"{SCREENSHOT_URL}/health", timeout=5)
        if resp.status_code == 200:
            st.success(f"Screenshot service online at `{SCREENSHOT_URL}`")
        else:
            st.warning(f"Screenshot service returned HTTP {resp.status_code}")
    except Exception as exc:
        st.warning(f"Screenshot service unreachable: {exc}")
