# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /build

# Install shared package first (matching other service patterns)
COPY shared/ /build/shared/
RUN pip install --no-cache-dir -e /build/shared/

WORKDIR /app

# Install service dependencies
COPY services/model_gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy service code
COPY services/model_gateway/ /app/

# Non-root user for security
RUN useradd -r -u 1001 -g 0 gateway && \
    mkdir -p /app/audit_logs /app/logs && \
    chown -R 1001:0 /app

USER 1001

EXPOSE 8400

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8400/health')"

CMD ["python", "app.py"]
