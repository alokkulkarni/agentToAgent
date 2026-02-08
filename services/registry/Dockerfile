FROM python:3.11-slim

WORKDIR /app

# Copy shared protocol
COPY shared/ /app/shared/

# Copy registry service
COPY services/registry/ /app/services/registry/

# Install dependencies
RUN pip install --no-cache-dir -r /app/services/registry/requirements.txt

# Expose port
EXPOSE 8000

# Run registry service
CMD ["python", "-m", "uvicorn", "services.registry.app:app", "--host", "0.0.0.0", "--port", "8000"]
