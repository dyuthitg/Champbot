# Standalone frontend image: builds and serves the React SPA on its own,
# talking to the backend as a separate origin (see VITE_API_BASE below).
# Build context for this Dockerfile is the frontend/ folder (Railway service
# root directory = frontend/), so all COPY paths below are relative to that.

FROM node:22-slim AS build
WORKDIR /app

# Vite bakes import.meta.env.VITE_* in at build time. Railway auto-forwards
# service variables as Docker build args for a Dockerfile builder, but only
# for ARGs a Dockerfile actually declares.
ARG VITE_CLERK_PUBLISHABLE_KEY
ARG VITE_API_BASE
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY \
    VITE_API_BASE=$VITE_API_BASE

COPY package.json ./
# npm install (not ci): the lock file is excluded from the Docker context.
RUN npm install --no-audit --no-fund
COPY . ./
RUN npm run build

# Runtime: serve the built static files with SPA fallback routing.
FROM node:22-slim
WORKDIR /app
RUN npm install -g serve@14 && \
    apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /app/dist ./dist

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f "http://localhost:${PORT:-3000}/" || exit 1

CMD ["sh", "-c", "serve -s dist -l ${PORT:-3000}"]
