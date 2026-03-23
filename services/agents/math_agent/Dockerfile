FROM python:3.13-slim

# Stage 1: install shared package
WORKDIR /build
COPY shared/ /build/shared/
RUN pip install --no-cache-dir /build/shared/

# Stage 2: install service dependencies
COPY services/agents/math_agent/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# Stage 3: copy service source flat
WORKDIR /app
COPY services/agents/math_agent/ /app/

# Expose port
EXPOSE 8006

CMD ["python", "app.py"]
