FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV DATA_DIR=/data
ENV RULES_DIR=/rules

COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api/app /app/app
COPY ingest /app/ingest
COPY rules /rules

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
