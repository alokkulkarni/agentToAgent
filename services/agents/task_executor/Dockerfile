FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/agents/task_executor/ /app/services/agents/task_executor/

RUN pip install --no-cache-dir -r /app/services/agents/task_executor/requirements.txt

EXPOSE 8004

CMD ["python", "services/agents/task_executor/app.py"]
