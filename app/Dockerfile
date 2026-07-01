# Citibike dashboard — Streamlit on Cloud Run.
# Serves the static parquet bundle baked into the image; no BigQuery at runtime.
# Python 3.12 matches the version the app was smoke-tested against.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer caches across code/data changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + bundled data (build context is the app/ directory).
COPY . .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

# Cloud Run injects $PORT (default 8080); Streamlit must bind it on 0.0.0.0.
EXPOSE 8080
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
