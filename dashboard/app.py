import streamlit as st
import requests
import hashlib
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="Lead Intelligence", layout="wide")

st.title("Lead Intelligence Dashboard")
st.caption("Real-time heatmap visualization for user interactions")

# Initialize session state
if "screenshot_timestamp" not in st.session_state:
    st.session_state.screenshot_timestamp = None

# Screenshot service URL
SCREENSHOT_SERVICE_URL = "http://localhost:8100"  # Adjust based on network

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

# Main dashboard layout
st.subheader("📸 Page Screenshot Viewer")

# URL selection
page_urls = [
    "https://example.com",
    "https://example.com/products",
    "https://example.com/about",
]

selected_url = st.selectbox("Select page to view:", page_urls, index=0)

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
    # Get screenshot paths
    url_hash = hashlib.sha256(selected_url.encode()).hexdigest()[:12]
    
    desktop_path = get_screenshot_path(url_hash, 1440)
    mobile_path = get_screenshot_path(url_hash, 390)
    
    # Tabs for viewport selection
    tab1, tab2 = st.tabs(["Desktop (1440px)", "Mobile (390px)"])
    
    with tab1:
        if desktop_path.exists():
            st.image(str(desktop_path), use_column_width=True, caption="Desktop viewport")
        else:
            st.info("📸 Click 'Refresh Screenshot' to capture the desktop view of this page")
    
    with tab2:
        if mobile_path.exists():
            st.image(str(mobile_path), use_column_width=True, caption="Mobile viewport")
        else:
            st.info("📱 Click 'Refresh Screenshot' to capture the mobile view of this page")
            
except Exception as e:
    st.error(f"Failed to load screenshots: {e}")

st.write("---")
st.info("💡 Screenshots provide the canvas for heatmap overlays in Phase 4. Refresh as needed to capture updated page versions.")
