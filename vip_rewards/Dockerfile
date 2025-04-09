# Dockerfile für jeden Service (log_collector, vip_rewards, stats_tracker)

FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py .
COPY service_name.py .  # z.B. log_collector.py, vip_rewards.py, etc.

CMD ["python", "service_name.py"]
