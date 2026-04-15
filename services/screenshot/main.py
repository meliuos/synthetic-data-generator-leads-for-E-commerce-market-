import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Screenshot Service", version="1.0.0")

SCREENSHOTS_DIR = Path("/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}


class CaptureRequest(BaseModel):
    url: str


class CaptureResponse(BaseModel):
    desktop: str
    mobile: str
    cached: bool
    url: str


def generate_url_hash(url: str) -> str:
    """Generate a short hash from URL for directory naming."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def get_screenshot_path(url_hash: str, viewport_name: str, viewport_width: int) -> Path:
    """Return path to screenshot file."""
    hash_dir = SCREENSHOTS_DIR / url_hash
    return hash_dir / f"{viewport_width}.png"


async def capture_screenshot_at_viewport(
    page, url: str, viewport_name: str, viewport_config: dict
) -> tuple[str, bool]:
    """
    Capture a screenshot at a specific viewport size.
    Returns (path_str, was_cached)
    """
    viewport_width = viewport_config["width"]
    url_hash = generate_url_hash(url)
    screenshot_path = get_screenshot_path(url_hash, viewport_name, viewport_width)

    # Check if already cached
    if screenshot_path.exists():
        logger.info(f"Using cached screenshot: {screenshot_path}")
        return str(screenshot_path), True

    # Set viewport and navigate
    await page.set_viewport_size(viewport_config)
    await page.goto(url, wait_until="networkidle", timeout=30000)

    # Wait for page to stabilize
    await asyncio.sleep(1)

    # Get full document height
    scrollHeight = await page.evaluate("document.body.scrollHeight")
    viewport_config["height"] = int(scrollHeight)

    # Create directory if needed
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    # Capture full page
    await page.screenshot(path=str(screenshot_path), full_page=True)
    logger.info(f"Captured screenshot: {screenshot_path}")

    return str(screenshot_path), False


@app.post("/capture", response_model=CaptureResponse)
async def capture_page(request: CaptureRequest) -> CaptureResponse:
    """
    Capture a page at desktop and mobile viewports.
    Screenshots are cached and reused for subsequent requests.
    """
    try:
        url = request.url

        # Validate URL
        if not url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid URL. Must start with http:// or https://",
            )

        url_hash = generate_url_hash(url)

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # Capture desktop
                desktop_path, desktop_cached = await capture_screenshot_at_viewport(
                    page, url, "desktop", VIEWPORTS["desktop"]
                )

                # Fresh page for mobile to ensure clean state
                await page.close()
                page = await context.new_page()

                # Capture mobile
                mobile_path, mobile_cached = await capture_screenshot_at_viewport(
                    page, url, "mobile", VIEWPORTS["mobile"]
                )

                # Consider cached if both are cached
                was_cached = desktop_cached and mobile_cached

                return CaptureResponse(
                    desktop=desktop_path,
                    mobile=mobile_path,
                    cached=was_cached,
                    url=url,
                )

            finally:
                await page.close()
                await context.close()
                await browser.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error capturing {request.url}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to capture screenshot: {str(e)}"
        )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return JSONResponse({"status": "ready"})


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "Screenshot Capture Service",
        "version": "1.0.0",
        "endpoints": {
            "capture": "POST /capture (url: string)",
            "health": "GET /health",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
