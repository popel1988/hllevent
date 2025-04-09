FROM python:3.9-slim

WORKDIR /app

COPY log_collector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY log_collector/log_collector.py .

CMD ["python", "log_collector.py"]
