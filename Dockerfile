# Multi-stage build: React SPA + FastAPI served as a single service.

# Stage 1: build the frontend
FROM node:22-slim AS frontend
WORKDIR /app/frontend
# Vite bakes import.meta.env.VITE_* in at build time, not read at runtime --
# a Railway *service variable* named VITE_CLERK_PUBLISHABLE_KEY does nothing
# on its own, because this build stage never saw it. Railway auto-forwards
# service variables as Docker build args for a Dockerfile builder, but only
# for ARGs a Dockerfile actually declares, which is why these two lines are
# the entire fix: without them the SPA silently built in demo mode -- no
# sign-in screen, no auth token ever attached, every API call 401ing behind
# an otherwise-normal-looking empty dashboard. Found live 2026-09-10.
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
COPY frontend/package.json ./
# npm install (not ci): the lock file is excluded from the Docker context.
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: install Python dependencies
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 3: minimal runtime image
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
COPY backend/src/ ./src/
COPY backend/main.py ./

# Migration tooling: the CMD below runs scripts/migrate.py before serving, and
# that script shells out to Alembic, which needs its config and script
# directory. All three were missing from every previous build of this image --
# the container passed its healthcheck-adjacent build step but crashed on
# every boot with "No such file or directory: scripts/migrate.py".
COPY backend/scripts/migrate.py ./scripts/migrate.py
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic/ ./alembic/

# Built SPA (served by FastAPI at /)
COPY --from=frontend /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/data /app/logs && chown -R appuser:appuser /app
USER appuser

# Schema is provisioned by Alembic in the start command below, so create_all is
# off here. Leaving both on would let a deploy quietly build tables that no
# migration describes, which is how a schema drifts out from under its history.
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
