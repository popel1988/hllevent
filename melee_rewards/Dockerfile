FROM python:3.9-slim

WORKDIR /app

COPY melee_rewards/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY melee_rewards/melee_rewards.py .

CMD ["python", "melee_rewards.py"]
