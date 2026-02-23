FROM python:3.11-slim

# Stage 1: install shared package
WORKDIR /build
COPY shared/ /build/shared/
RUN pip install --no-cache-dir /build/shared/

# Stage 2: install service dependencies
COPY services/agents/task_executor/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

# Stage 3: copy service source flat
WORKDIR /app
COPY services/agents/task_executor/ /app/

EXPOSE 8004

CMD ["python", "app.py"]
