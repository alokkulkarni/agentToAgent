FROM python:3.11-slim

WORKDIR /app

# Copy shared protocol
COPY shared/ /app/shared/

# Copy agent service
COPY services/agents/code_analyzer/ /app/services/agents/code_analyzer/

# Install dependencies
RUN pip install --no-cache-dir -r /app/services/agents/code_analyzer/requirements.txt

# Expose port
EXPOSE 8001

# Run agent service
CMD ["python", "services/agents/code_analyzer/app.py"]
