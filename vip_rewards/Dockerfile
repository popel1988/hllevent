FROM python:3.9-slim

WORKDIR /app

COPY vip_rewards/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vip_rewards/vip_rewards.py .

CMD ["python", "vip_rewards.py"]
