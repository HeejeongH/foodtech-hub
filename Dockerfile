FROM python:3.11-slim

WORKDIR /app

# System deps (lxml/pandas wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY app.py .
COPY static/ ./static/

# Data dir for cache (mount volume in production)
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

# IMPORTANT: Do NOT hardcode ENV PORT here.
# Railway/Render inject $PORT at runtime; hardcoding overrides it.
EXPOSE 8000

# Use sh -c so $PORT expands at container start.
# Fall back to 8000 only for local docker runs without PORT set.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
