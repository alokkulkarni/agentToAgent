FROM python:3.11-slim

WORKDIR /app

# Copy shared protocol
COPY shared/ /app/shared/

# Copy orchestrator service
COPY services/orchestrator/ /app/services/orchestrator/

# Install dependencies
RUN pip install --no-cache-dir -r /app/services/orchestrator/requirements.txt

# Expose port
EXPOSE 8100

# Run orchestrator service
CMD ["python", "services/orchestrator/app.py"]
