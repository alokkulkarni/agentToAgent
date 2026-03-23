FROM python:3.13-slim

# Stage 1: install shared package
WORKDIR /build
COPY shared/ /build/shared/
RUN pip install --no-cache-dir /build/shared/

# Stage 2: install service dependencies
COPY services/mcp_servers/calculator/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# Stage 3: copy service source flat
WORKDIR /app
COPY services/mcp_servers/calculator/ /app/

# Expose port
EXPOSE 8213

CMD ["python", "app.py"]
