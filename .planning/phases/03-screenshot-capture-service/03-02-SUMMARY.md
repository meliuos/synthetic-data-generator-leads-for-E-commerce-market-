---
phase: 03-screenshot-capture-service
plan: 02
created: 2026-04-15
status: implemented
---

# Plan 03-02 Summary: Dashboard Screenshot Integration

## Objective
Integrate screenshot display and refresh controls into the Streamlit dashboard, enabling users to view captured screenshots at both desktop and mobile viewports and trigger new captures on demand.

## Implementation Status

### Completed
1. **Dashboard App** (dashboard/app.py)
   - URL selectbox with predefined test URLs (example.com variations)
   - Refresh button with loading spinner
   - Session state tracking for last capture timestamp
   - capture_screenshot(url) function that calls POST /capture on screenshot service
   - get_screenshot_path(hash, viewport) function for local file access
   - Tab-based viewport selector (Desktop 1440px | Mobile 390px)
   - Conditional image display (shows placeholder if not yet captured)
   - Error handling for unreachable service with helpful messages
   - Graceful fallback if service unavailable (no dashboard crash)

2. **Dependencies** (dashboard/requirements.txt)
   - streamlit==1.44.1
   - clickhouse-connect==0.8.13
   - requests==2.31.0 (added for service integration)

3. **Service Integration**
   - SCREENSHOT_SERVICE_URL = "http://localhost:8100" (configurable)
   - POST to /capture endpoint with {url} payload
   - 60-second timeout for long-running captures
   - Parses JSON response: {desktop, mobile, cached, url}
   - Displays "cached" badge when using cached screenshots

## Deliverables
- ✅ Dashboard displays "📸 Page Screenshot Viewer" section
- ✅ URL selectbox for choosing pages to screenshot
- ✅ "🔄 Refresh Screenshot" button with spinner
- ✅ Last capture timestamp display
- ✅ Desktop (1440px) and Mobile (390px) tabs for viewport switching
- ✅ Placeholder cards if screenshots not yet captured
- ✅ Cached vs freshly captured status indicator
- ✅ Seamless st.rerun() after capture to display images
- ✅ Error handling with user-friendly messages

## Implementation Notes
- Uses hashlib.sha256() to compute same URL hash as service (first 12 chars)
- Screenshot paths: ./screenshots/{hash}/{1440|390}.png
- Session state persists timestamp across reruns
- Refresh button disabled while capture is in progress (st.spinner handling)
- URLs in selectbox are placeholders; production would load from database
- Service URL configurable: easy to point to different host/port
- Graceful degradation if service down (shows error, not crash)

## Architecture
```
Dashboard (Streamlit)
    |
    v
Screenshot Service (FastAPI)
    |
    v
Playwright (chromium)
    |
    v
./screenshots/{hash}/1440.png
./screenshots/{hash}/390.png
```

## Next Steps (Phase 04)
Phase 04 will overlay Plotly heatmaps on these screenshots, using the same URL selector and viewport tabs to display click/scroll/hover heat distributions.

## Verification Checklist
- [ ] Dashboard app.py imports requests successfully
- [ ] Streamlit starts without errors: `docker compose up streamlit`
- [ ] Screenshot viewer section visible on dashboard
- [ ] URL selectbox populated with test URLs
- [ ] "Refresh Screenshot" button responds to clicks
- [ ] Spinner shows while capturing
- [ ] Both desktop and mobile tabs render correctly
- [ ] Images display when screenshots exist locally
- [ ] Cached vs fresh status shown correctly
- [ ] Refresh faster on second click (cache hit)
- [ ] Error message shows if screenshot service unreachable
- [ ] No dashboard crashes on service errors

## Files Modified
- dashboard/app.py (full rewrite with screenshot functionality)
- dashboard/requirements.txt (added requests==2.31.0)

## Git Commit
```
feat(phase-03): implement screenshot service and dashboard integration
```
Includes service code, Dockerfile, docker-compose config, and dashboard UI.
