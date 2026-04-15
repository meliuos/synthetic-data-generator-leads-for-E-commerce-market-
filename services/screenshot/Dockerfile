FROM debian:bookworm-slim

# Install Python and system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    python3.11 python3-pip python3-venv \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libpango-1.0-0 libcairo2 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libxinerama1 libxcursor1 \
    libxtst6 fonts-liberation \
    ca-certificates curl wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY services/screenshot/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Install Playwright browsers with their system dependencies
RUN python3 -m playwright install chromium && python3 -m playwright install-deps chromium

# Copy application
COPY services/screenshot/main.py .

# Create screenshots directory
RUN mkdir -p /screenshots && chmod 777 /screenshots

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
