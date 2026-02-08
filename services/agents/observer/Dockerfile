FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/agents/observer/ /app/services/agents/observer/

RUN pip install --no-cache-dir -r /app/services/agents/observer/requirements.txt

EXPOSE 8005

CMD ["python", "services/agents/observer/app.py"]
