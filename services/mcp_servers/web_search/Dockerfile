FROM python:3.13-slim

WORKDIR /app

# Copy web search server files
COPY services/mcp_servers/web_search/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/mcp_servers/web_search/ .

# Expose port
EXPOSE 8212

CMD ["python", "app.py"]
