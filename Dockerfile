FROM python:3.11-slim

WORKDIR /app

# Install deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .
COPY static/ ./static/

# Data dir for cache (mounted as volume in production)
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

# Cloud platforms set PORT; default 8000
ENV PORT=8000
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8000\")}/api/health', timeout=3)" || exit 1

# Bind to 0.0.0.0:$PORT (shell form expands env var)
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
