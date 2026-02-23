FROM python:3.11-slim

# Stage 1: install shared package
WORKDIR /build
COPY shared/ /build/shared/
RUN pip install --no-cache-dir /build/shared/

# Stage 2: install service dependencies
COPY services/registry/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# Stage 3: copy service source flat
WORKDIR /app
COPY services/registry/ /app/

# Expose port
EXPOSE 8000

# Run registry service
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
