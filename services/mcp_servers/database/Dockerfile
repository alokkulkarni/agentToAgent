FROM python:3.13-slim

WORKDIR /app

# Copy database server files
COPY services/mcp_servers/database/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/mcp_servers/database/ .

# Create database directory
RUN mkdir -p /tmp

# Expose port
EXPOSE 8211

CMD ["python", "app.py"]
