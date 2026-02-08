FROM python:3.13-slim

WORKDIR /app

# Copy file operations server files
COPY services/mcp_servers/file_ops/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/mcp_servers/file_ops/ .

# Create workspace directory
RUN mkdir -p /tmp/mcp_workspace

# Expose port
EXPOSE 8210

CMD ["python", "app.py"]
