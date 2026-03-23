FROM python:3.11-slim

# ── Stage 1: install the shared library as a proper Python package ──────────
# `shared/` is copied first so Docker layer-caching skips re-install when only
# orchestrator source files change.
WORKDIR /build
COPY shared/ /build/shared/
RUN pip install --no-cache-dir /build/shared/

# ── Stage 2: install service-specific dependencies ──────────────────────────
COPY services/orchestrator/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# ── Stage 3: copy orchestrator source into a clean flat workdir ─────────────
# The service runs directly from /app — no nested services/orchestrator/ path.
# `shared` is already installed site-wide, so no sys.path tricks are needed.
WORKDIR /app
COPY services/orchestrator/ /app/

# Expose port
EXPOSE 8100

# Run service
CMD ["python", "app.py"]
