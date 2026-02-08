FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/agents/data_processor/ /app/services/agents/data_processor/

RUN pip install --no-cache-dir -r /app/services/agents/data_processor/requirements.txt

EXPOSE 8002

CMD ["python", "services/agents/data_processor/app.py"]
