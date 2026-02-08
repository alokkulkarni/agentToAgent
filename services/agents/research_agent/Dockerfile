FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
COPY services/agents/research_agent/ /app/services/agents/research_agent/

RUN pip install --no-cache-dir -r /app/services/agents/research_agent/requirements.txt

EXPOSE 8003

CMD ["python", "services/agents/research_agent/app.py"]
