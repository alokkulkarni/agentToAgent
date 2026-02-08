FROM python:3.13-slim

WORKDIR /app

# Copy calculator server files
COPY services/mcp_servers/calculator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/mcp_servers/calculator/ .

# Expose port
EXPOSE 8213

CMD ["python", "app.py"]
