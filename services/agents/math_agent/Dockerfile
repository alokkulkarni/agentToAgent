FROM python:3.13-slim

WORKDIR /app

# Copy shared protocol files
COPY shared/ /app/shared/

# Copy agent files
COPY services/agents/math_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/agents/math_agent/ .

# Expose port
EXPOSE 8006

CMD ["python", "app.py"]
