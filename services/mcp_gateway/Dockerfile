FROM python:3.13-slim

WORKDIR /app

# Copy MCP gateway files
COPY services/mcp_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/mcp_gateway/ .

# Expose port
EXPOSE 8300

CMD ["python", "app.py"]
