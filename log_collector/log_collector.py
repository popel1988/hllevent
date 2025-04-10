#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime, timezone
import redis
import os
import threading
from config import API_URL, API_KEY, REDIS_HOST, REDIS_PORT  # Laden aus config.py

# Redis-Konfiguration
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

# Gesehene Log-IDs und letzter Zeitstempel
seen_log_ids = set()
last_timestamp = datetime.now(timezone.utc).isoformat()

# Lock für Thread-Sicherheit
lock = threading.Lock()

def fetch_logs(action, limit=15):
    """Holt Logs von der API für eine bestimmte Aktion."""
    global last_timestamp
    payload = {
        "action": action,
        "limit": limit,
        "after": last_timestamp
    }

    try:
        response = requests.post(f"{API_URL}/api/get_historical_logs", headers={"Authorization": f"Bearer {API_KEY}"}, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("result", [])
    except requests.exceptions.RequestException as e:
        print(f"Fehler beim Abrufen von Logs ({action}): {e}")
        return []

def process_logs(logs):
    """Verarbeitet und veröffentlicht neue Logs."""
    global last_timestamp
    new_logs = [log for log in logs if log["id"] not in seen_log_ids]

    for log in sorted(new_logs, key=lambda x: x["event_time"]):
        print(json.dumps(log, indent=2))  # Debug: Log anzeigen
        seen_log_ids.add(log["id"])
        r.publish('game_logs', json.dumps(log))  # Sende Log an Redis

        # Aktualisiere den letzten Zeitstempel
        last_timestamp = log["event_time"]

def fetch_and_process_kills():
    """Holt und verarbeitet KILL-Logs."""
    while True:
        try:
            logs = fetch_logs("KILL", limit=15)
            if logs:
                with lock:
                    process_logs(logs)
        except Exception as e:
            print(f"Fehler beim Verarbeiten von KILL-Logs: {e}")

        time.sleep(5)  # Warte 5 Sekunden vor der nächsten Anfrage

def fetch_and_process_match_ended():
    """Holt und verarbeitet MATCH ENDED-Logs."""
    while True:
        try:
            logs = fetch_logs("MATCH ENDED", limit=1)
            if logs:
                with lock:
                    process_logs(logs)
        except Exception as e:
            print(f"Fehler beim Verarbeiten von MATCH ENDED-Logs: {e}")

        time.sleep(15)  # Warte 15 Sekunden vor der nächsten Anfrage

def main():
    """Hauptfunktion des Log Collectors."""
    print("Log Collector gestartet. Warte auf Events...")

    # Starte separate Threads für KILL- und MATCH ENDED-Logs
    threading.Thread(target=fetch_and_process_kills, daemon=True).start()
    threading.Thread(target=fetch_and_process_match_ended, daemon=True).start()

    # Hauptprozess bleibt am Leben
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
