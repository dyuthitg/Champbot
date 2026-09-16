# Standalone backend image: FastAPI service only, no frontend build/serve.
# Build context for this Dockerfile is the backend/ folder (Railway service
# root directory = backend/), so all COPY paths below are relative to that.

# Stage 1: install Python dependencies
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: minimal runtime image
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser

# Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Application code
COPY src/ ./src/
COPY main.py ./

# Migration tooling: the CMD below runs scripts/migrate.py before serving, and
# that script shells out to Alembic, which needs its config and script
# directory.
COPY scripts/migrate.py ./scripts/migrate.py
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

# No frontend/dist here on purpose -- this image serves the API only. The SPA
# is a separate Railway service built from frontend/Dockerfile; src/api/main.py
# no-ops its static-file mount when frontend/dist is absent.

RUN mkdir -p /app/data /app/logs && chown -R appuser:appuser /app
USER appuser

# Schema is provisioned by Alembic in the start command below, so create_all is
# off here.
ENV AUTO_CREATE_TABLES=false \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Railway/most PaaS inject $PORT; default to 8000 locally.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f "http://localhost:${PORT:-8000}/healthz" || exit 1

# Migrate, then serve. The `&&` is load-bearing: if the schema cannot be brought
# to head the container must fail its healthcheck rather than serve traffic
# against a database it disagrees with.
CMD ["sh", "-c", "python scripts/migrate.py && uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
