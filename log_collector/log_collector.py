#!/usr/bin/env python3
import requests
import json
import time
import threading
from datetime import datetime, timezone
import redis
import os
from config import API_URL, API_TOKEN, REDIS_HOST, REDIS_PORT  # Laden aus config.py

# Redis-Verbindung
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

# Speicher für bereits gesehene Log-IDs
seen_log_ids = set()

# Initialer Zeitstempel
last_timestamp = datetime.now(timezone.utc).isoformat()

# Lock für Thread-Sicherheit
match_ended_lock = threading.Lock()

def match_ended_poller():
    """Pollt unabhängig MATCH ENDED Events"""
    global last_timestamp
    while True:
        try:
            with match_ended_lock:
                match_ended_payload = {
                    "action": "MATCH ENDED",
                    "limit": 1,
                    "after": last_timestamp
                }
                
                response = requests.post(f"{API_URL}/api/get_historical_logs", headers={"Authorization": f"Bearer {API_TOKEN}"}, json=match_ended_payload)
                response.raise_for_status()
                data = response.json()
                
                if data["result"]:
                    handle_match_ended(data["result"])
        
        except Exception as e:
            print(f"Fehler im MATCH ENDED Poller: {e}")
        
        # Polling-Intervall (z.B. 15 Sekunden)
        time.sleep(15)

def handle_match_ended(logs):
    """Verarbeitet MATCH ENDED Events"""
    global last_timestamp
    for log in sorted(logs, key=lambda x: x["event_time"]):
        if log["id"] not in seen_log_ids:
            print(json.dumps(log, indent=2))  # Debug-Ausgabe
            seen_log_ids.add(log["id"])
            r.publish('game_logs', json.dumps(log))  # An Redis senden

            # Aktualisiere den Zeitstempel
            last_timestamp = log["event_time"]

# Separater Thread für MATCH ENDED Polling
threading.Thread(target=match_ended_poller, daemon=True).start()

while True:
    try:
        kill_payload = {
            "action": "KILL",
            "limit": 15,
            "after": last_timestamp
        }

        response = requests.post(f"{API_URL}/api/get_historical_logs", headers={"Authorization": f"Bearer {API_TOKEN}"}, json=kill_payload)
        response.raise_for_status()
        kill_data = response.json()

        if kill_data["result"]:
            # Sortiere und verarbeite nur neue Logs
            sorted_logs = sorted(kill_data["result"], key=lambda x: x["event_time"])
            new_logs = [log for log in sorted_logs if log["id"] not in seen_log_ids]

            for log in new_logs:
                print(json.dumps(log, indent=2))  # Debug-Ausgabe
                seen_log_ids.add(log["id"])
                r.publish('game_logs', json.dumps(log))  # An Redis senden

            # Aktualisiere den Zeitstempel
            if new_logs:
                last_timestamp = new_logs[-1]["event_time"]

        # Pause vor der nächsten Anfrage
        time.sleep(5)

    except Exception as e:
        print(f"Fehler im Haupt-Polling: {e}")
        time.sleep(10)  # Längere Pause bei Fehlern
