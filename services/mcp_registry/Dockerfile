FROM python:3.13-slim

WORKDIR /app

# Copy MCP registry files
COPY services/mcp_registry/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/mcp_registry/ .

# Expose port
EXPOSE 8200

CMD ["python", "app.py"]
