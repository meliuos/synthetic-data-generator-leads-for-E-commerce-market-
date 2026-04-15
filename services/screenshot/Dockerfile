FROM mcr.microsoft.com/playwright/python:v1.40.0

WORKDIR /app

# Copy requirements and install Python dependencies
COPY services/screenshot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY services/screenshot/main.py .

# Create screenshots directory
RUN mkdir -p /screenshots

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
