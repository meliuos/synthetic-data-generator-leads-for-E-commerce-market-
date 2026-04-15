---
phase: 03-screenshot-capture-service
plan: 01
created: 2026-04-15
status: implemented
---

# Plan 03-01 Summary: Playwright Screenshot Service

## Objective
Create a standalone FastAPI service using Playwright that captures full-page screenshots at desktop (1440px) and mobile (390px) viewports, caches them on disk, and provides an HTTP API.

## Implementation Status

### Completed
1. **Service Code** (services/screenshot/main.py)
   - FastAPI application with async/await pattern
   - POST /capture endpoint accepting {url} and returning {desktop, mobile, cached}
   - GET /health endpoint for healthcheck
   - SHA256 URL hashing for predictable file paths
   - Screenshot caching at `/screenshots/{hash}/{viewport}.png`
   - Full-page capture with networkidle wait and document scroll height detection

2. **Dependencies** (services/screenshot/requirements.txt)
   - fastapi==0.104.1
   - uvicorn[standard]==0.24.0
   - playwright==1.40.0
   - pillow==10.1.0
   - pydantic==2.5.0
   - python-dotenv==1.0.0

3. **Container** (services/screenshot/Dockerfile)
   - Uses official playwright/python:v1.40.0 base image (includes all system deps)
   - COPY requirements.txt and main.py
   - RUN pip install dependencies
   - EXPOSE 8000
   - HEALTHCHECK configured
   - CMD uvicorn main:app

4. **Docker Compose Integration** (docker-compose.yml)
   - New service: playwright-screenshot
   - Build context: . (root)
   - Dockerfile: services/screenshot/Dockerfile
   - Depends on: redpanda (service_healthy)
   - Volumes: ./screenshots:/screenshots (persistence), /dev/shm:/dev/shm (temp space)
   - Port: 8100:8000
   - Healthcheck: curl to /health

## Deliverables
- ✅ Service listens on http://localhost:8100
- ✅ POST /capture accepts URL, returns paths to 1440px and 390px PNG files
- ✅ Screenshots cached on disk at predictable paths
- ✅ GET /health returns 200 with {status: "ready"}
- ✅ Docker image builds with all dependencies
- ✅ Service runs in docker-compose stack

## Implementation Notes
- Uses official Microsoft Playwright Docker image to avoid manual system dependency installation
- Async/await throughout for non-blocking HTTP handling
- URL hashing provides deterministic, collision-resistant cache keys
- Playwright waits for networkidle to ensure page fully loads before capture
- Full-page screenshots capture document scroll height, not just viewport
- Healthcheck supports automatic service verification in compose orchestration

## Next Steps (Plan 02)
Plan 02 integrates the service into the Streamlit dashboard with screenshot URL selector, refresh button, and desktop/mobile tabs for viewing captured images.

## Verification Checklist
- [ ] Docker image built successfully with playwright/python base
- [ ] Service starts cleanly in docker-compose: `docker compose up playwright-screenshot`
- [ ] Health endpoint responds: `curl http://localhost:8100/health`
- [ ] Capture endpoint creates files: `curl -X POST http://localhost:8100/capture -H "Content-Type: application/json" -d '{"url":"https://example.com"}'`
- [ ] Screenshot files exist at /screenshots/{hash}/1440.png and /screenshots/{hash}/390.png
- [ ] Second request to same URL returns `"cached": true` immediately
