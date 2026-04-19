import hashlib
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from heatmap_filters import normalize_url_filter
from heatmap_queries import (
    fetch_click_ranking,
    fetch_heatmap_aggregates_for,
    fetch_session_stats,
)
from heatmap_views import build_heatmap_figure_for_mode

st.set_page_config(page_title="Lead Intelligence", layout="wide")

st.title("Lead Intelligence Dashboard")
st.caption("Real-time heatmap visualization for user interactions")

# Initialize session state
if "screenshot_timestamp" not in st.session_state:
    st.session_state.screenshot_timestamp = None

# Screenshot service URL
SCREENSHOT_SERVICE_URL = os.getenv("SCREENSHOT_SERVICE_URL", "http://localhost:8100")
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "analytics")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "analytics")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "analytics_password")


PAGE_URLS = [
    "http://host.docker.internal:5000/src/test-spa-page.html",
    "http://host.docker.internal:5000/src/test-spa-page.html?variant=checkout",
    "http://host.docker.internal:5000/src/test-spa-page.html?variant=pricing",
]

VIEWPORTS = {
    "Desktop (1440px)": (1440, 900),
    "Mobile (390px)": (390, 844),
}

HEATMAP_MODES = {
    "Click": "click",
    "Scroll": "scroll",
    "Hover": "mousemove",
}

def capture_screenshot(url: str) -> dict:
    """Call screenshot service to capture URL at both viewports."""
    try:
        response = requests.post(
            f"{SCREENSHOT_SERVICE_URL}/capture",
            json={"url": url},
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Failed to capture screenshot: {e}")
        return None

def get_screenshot_path(url_hash: str, viewport: int) -> Path:
    """Return path to cached screenshot."""
    return Path("./screenshots") / url_hash / f"{viewport}.png"


def get_clickhouse_client():
    """Create a ClickHouse client from environment settings."""
    try:
        import clickhouse_connect
    except ImportError as exc:
        st.error(f"ClickHouse client dependency missing: {exc}")
        return None

    try:
        return clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )
    except Exception as exc:
        st.error(f"Failed to connect to ClickHouse: {exc}")
        return None


def load_heatmap_dataframe(
    url_filter: str,
    event_type: str,
    viewport_width: int,
    viewport_height: int,
):
    """Fetch pre-binned heatmap data for the selected page and mode."""
    client = get_clickhouse_client()
    if client is None:
        return pd.DataFrame(columns=["x_bin_pct", "y_bin_pct", "event_count"])

    try:
        return fetch_heatmap_aggregates_for(
            client,
            url_filter=url_filter,
            event_type=event_type,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
    except Exception as exc:
        st.error(f"Failed to load heatmap data: {exc}")
        return pd.DataFrame(columns=["x_bin_pct", "y_bin_pct", "event_count"])


def load_session_stats_dataframe(url_filter: str):
    """Fetch one-row aggregate session stats for the selected URL scope."""
    client = get_clickhouse_client()
    if client is None:
        return pd.DataFrame(
            [
                {
                    "total_sessions": 0,
                    "avg_scroll_depth_pct": 0.0,
                    "bounce_rate_pct": 0.0,
                    "total_events": 0,
                }
            ]
        )

    try:
        return fetch_session_stats(client, url_filter)
    except Exception as exc:
        st.error(f"Failed to load session stats: {exc}")
        return pd.DataFrame(
            [
                {
                    "total_sessions": 0,
                    "avg_scroll_depth_pct": 0.0,
                    "bounce_rate_pct": 0.0,
                    "total_events": 0,
                }
            ]
        )


def load_click_ranking_dataframe(url_filter: str):
    """Fetch top-clicked CSS selectors for the selected URL scope."""
    client = get_clickhouse_client()
    if client is None:
        return pd.DataFrame(columns=["element_selector", "click_count"])

    try:
        return fetch_click_ranking(client, url_filter, limit=10)
    except Exception as exc:
        st.error(f"Failed to load click ranking: {exc}")
        return pd.DataFrame(columns=["element_selector", "click_count"])


def render_heatmap_tab(
    selected_url: str,
    viewport_label: str,
    viewport_width: int,
    viewport_height: int,
    url_filter: str,
    event_type: str,
    mode_label: str,
) -> None:
    """Render one viewport tab with the screenshot-backed heatmap overlay."""
    url_hash = hashlib.sha256(selected_url.encode()).hexdigest()[:12]
    screenshot_path = get_screenshot_path(url_hash, viewport_width)

    if not screenshot_path.exists():
        st.info(f"{viewport_label}: click 'Refresh Screenshot' to capture this view")
        return

    dataframe = load_heatmap_dataframe(url_filter, event_type, viewport_width, viewport_height)
    if getattr(dataframe, "empty", True):
        st.caption(f"{viewport_label}: no {mode_label.lower()} events found yet; showing the screenshot canvas")

    try:
        figure = build_heatmap_figure_for_mode(
            event_type,
            screenshot_path,
            dataframe,
            viewport_width,
            viewport_height,
            title=f"{viewport_label} {mode_label.lower()} heatmap",
        )
        st.plotly_chart(figure, use_container_width=True)
    except Exception as exc:
        st.error(f"Failed to render {viewport_label.lower()} heatmap: {exc}")

# Main dashboard layout
st.subheader("📸 Page Screenshot Viewer")

# URL selection
selected_url = st.selectbox("Select page to view:", PAGE_URLS, index=0)
wildcard_filter = st.text_input(
    "Optional wildcard scope",
    value="",
    placeholder="/product/*",
    help="Leave blank to query only the selected page, or use * to scope a family of pages.",
)
selected_mode_label = st.radio("Heatmap mode", list(HEATMAP_MODES.keys()), horizontal=True)
selected_event_type = HEATMAP_MODES[selected_mode_label]
active_url_filter = normalize_url_filter(selected_url, wildcard_filter)

session_stats_df = load_session_stats_dataframe(active_url_filter)
click_ranking_df = load_click_ranking_dataframe(active_url_filter)

st.subheader("Session Stats")
if getattr(session_stats_df, "empty", True) or int(session_stats_df.iloc[0]["total_sessions"]) == 0:
    st.info("No sessions yet")
else:
    stats_row = session_stats_df.iloc[0]
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    stat_col1.metric("Total sessions", int(stats_row["total_sessions"]))
    stat_col2.metric("Avg scroll depth", f"{float(stats_row['avg_scroll_depth_pct']):.2f}%")
    stat_col3.metric(
        "Bounce rate",
        f"{float(stats_row['bounce_rate_pct']):.2f}%",
        help="Bounce rate = sessions with exactly one page_view event / total sessions for the selected URL scope.",
    )
    stat_col4.metric("Total events", int(stats_row["total_events"]))

st.subheader("Top Clicked Selectors")
if getattr(click_ranking_df, "empty", True):
    st.info("No clicks yet")
else:
    ranking_display_df = click_ranking_df.rename(
        columns={"element_selector": "CSS selector", "click_count": "Clicks"}
    )
    st.dataframe(ranking_display_df, use_container_width=True, hide_index=True)

st.write("---")

# Refresh button
col1, col2 = st.columns([1, 3])
with col1:
    refresh_button = st.button("🔄 Refresh Screenshot", key="refresh_btn")
with col2:
    if st.session_state.screenshot_timestamp:
        st.caption(f"Last updated: {st.session_state.screenshot_timestamp}")
    else:
        st.caption("Not yet captured")

# Refresh action
if refresh_button:
    with st.spinner("Capturing screenshot... this may take up to 30 seconds"):
        result = capture_screenshot(selected_url)
        if result:
            st.session_state.screenshot_timestamp = datetime.now().strftime("%H:%M:%S")
            cached_str = "cached" if result.get("cached") else "freshly captured"
            st.success(f"✓ Screenshot {cached_str}")
            st.rerun()

# Display screenshots
st.write("---")

try:
    desktop_tab, mobile_tab = st.tabs(list(VIEWPORTS.keys()))

    with desktop_tab:
        desktop_width, desktop_height = VIEWPORTS["Desktop (1440px)"]
        render_heatmap_tab(
            selected_url,
            "Desktop (1440px)",
            desktop_width,
            desktop_height,
            active_url_filter,
            selected_event_type,
            selected_mode_label,
        )

    with mobile_tab:
        mobile_width, mobile_height = VIEWPORTS["Mobile (390px)"]
        render_heatmap_tab(
            selected_url,
            "Mobile (390px)",
            mobile_width,
            mobile_height,
            active_url_filter,
            selected_event_type,
            selected_mode_label,
        )
            
except Exception as e:
    st.error(f"Failed to load screenshots: {e}")

st.write("---")
st.info("💡 Screenshots provide the canvas for Plotly heatmap overlays in Phase 4. Refresh as needed to capture updated page versions.")
