#!/usr/bin/env python3
import requests
import json
import time
from datetime import datetime, timezone
import redis
import os
from config import API_URL, API_KEY, REDIS_HOST, REDIS_PORT

# Redis-Verbindung
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

# API-Konfiguration
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Speicher für bereits gesehene Log-IDs
seen_log_ids = set()

# Initialer Zeitstempel
last_timestamp = datetime.now(timezone.utc).isoformat()

while True:
    try:
        # Mehrere API-Anfragen für verschiedene Event-Typen
        all_new_logs = []
        
        # Abfrage für KILL-Events
        kill_payload = {
            "action": "KILL",
            "limit": 15,
            "after": last_timestamp
        }
        
        kill_response = requests.post(f"{API_URL}/api/get_historical_logs", headers=headers, json=kill_payload)
        kill_response.raise_for_status()
        kill_data = kill_response.json()
        
        if kill_data["result"]:
            all_new_logs.extend(kill_data["result"])
        
        # Abfrage für MATCH ENDED-Events
        match_ended_payload = {
            "action": "MATCH ENDED",
            "limit": 5,
            "after": last_timestamp
        }
        
        match_ended_response = requests.post(f"{API_URL}/api/get_historical_logs", headers=headers, json=match_ended_payload)
        match_ended_response.raise_for_status()
        match_ended_data = match_ended_response.json()
        
        if match_ended_data["result"]:
            all_new_logs.extend(match_ended_data["result"])
        
        # Verarbeiten aller Logs
        if all_new_logs:
            # Sortieren der Logs nach event_time (neueste zuletzt)
            sorted_logs = sorted(all_new_logs, key=lambda x: x["event_time"])
            
            # Nur neue Logs anzeigen und an Redis senden
            new_logs = [log for log in sorted_logs if log["id"] not in seen_log_ids]
            
            for log in new_logs:
                print(json.dumps(log, indent=2))
                seen_log_ids.add(log["id"])
                # Log an Redis-Channel senden
                r.publish('game_logs', json.dumps(log))
            
            # Zeitstempel aktualisieren (nur wenn neue Logs vorhanden sind)
            if new_logs:
                last_timestamp = new_logs[-1]["event_time"]
                print(f"\n--- Letzter Zeitstempel: {last_timestamp} ---\n")
        
        # Pause vor der nächsten Anfrage
        time.sleep(5)
        
    except Exception as e:
        print(f"Fehler: {e}")
        time.sleep(10)  # Längere Pause bei Fehlern
