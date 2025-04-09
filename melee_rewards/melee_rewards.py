#!/usr/bin/env python3
import redis
import json
import time
import requests
from datetime import datetime, timezone
import pytz
from config import API_URL, API_KEY, REDIS_HOST, REDIS_PORT

# Redis-Verbindung
try:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    ping_response = r.ping()
    print(f"Redis-Verbindung erfolgreich: {ping_response}")
except Exception as e:
    print(f"Redis-Verbindungsfehler: {e}")
    exit(1)

pubsub = r.pubsub()

# API-Konfiguration
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Melee-Waffen Liste
MELEE_WEAPONS = ["M3 Knife", "Feldspaten"]

# VIP-Belohnungsdauer in Stunden
VIP_DURATION_HOURS = 24  # 1 Tag

def convert_utc_to_local(utc_time_str):
    """Konvertiert einen UTC-Zeitstempel in lokale Zeit (CEST)"""
    utc_time = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
    local_tz = pytz.timezone('Europe/Berlin')
    local_time = utc_time.astimezone(local_tz)
    return local_time.strftime('%Y-%m-%d %H:%M:%S %Z')

def grant_vip_status(player_id, player_name, weapon):
    """Gewährt einem Spieler VIP-Status über die API"""
    data = {
        "player_id": player_id,
        "description": f"Belohnung für einen Kill mit {weapon}",
        "expiration": f"{VIP_DURATION_HOURS}h"
    }
    
    response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
    if response.status_code == 200:
        print(f"VIP-Status erfolgreich für {player_name} (ID: {player_id}) gewährt")
        return True
    else:
        print(f"Fehler beim Gewähren des VIP-Status: {response.status_code}, Antwort: {response.text}")
        return False

def message_player(player_id, message):
    """Sendet eine Nachricht an einen bestimmten Spieler"""
    data = {
        "player_id": player_id,
        "message": message,
        "by": "Melee Kill Reward System",
        "save_message": True
    }
    
    response = requests.post(f"{API_URL}/api/message_player", headers=headers, json=data)
    if response.status_code == 200:
        print(f"Nachricht erfolgreich an Spieler {player_id} gesendet")
        return True
    else:
        print(f"Fehler beim Senden der Nachricht an Spieler {player_id}: {response.status_code}, Antwort: {response.text}")
        return False

def process_melee_kill(log_data):
    """Verarbeitet einen Melee-Kill und belohnt den Spieler"""
    killer_name = log_data["player1_name"]
    killer_id = log_data["player1_id"]
    victim_name = log_data["player2_name"]
    weapon = log_data["weapon"]
    
    local_time = convert_utc_to_local(log_data["event_time"])
    print(f"\n=== MELEE KILL ERKANNT: {local_time} ===")
    print(f"{killer_name} hat {victim_name} mit {weapon} getötet!")
    
    if grant_vip_status(killer_id, killer_name, weapon):
        message = f"Gratulation! Du hast {victim_name} mit {weapon} eliminiert und erhältst {VIP_DURATION_HOURS} Stunden VIP-Status!"
        message_player(killer_id, message)
        print(f"VIP-Status und Benachrichtigung für {killer_name} verarbeitet.")

# Den game_logs Channel abonnieren
pubsub.subscribe('game_logs')
print(f"Erfolgreich 'game_logs' Channel abonniert auf {REDIS_HOST}:{REDIS_PORT}")

print("Melee-Kill VIP-Belohnungs-Service gestartet. Warte auf Kill-Events...")

# Nachricht zum Überspringen der Bestätigungsnachricht
pubsub.get_message()

try:
    while True:
        message = pubsub.get_message()
        
        if message:
            print(f"Nachricht empfangen: {message['type']}")
            if message['type'] == 'message':
                print(f"Daten empfangen: {message['data'][:100]}...")  # Ersten 100 Zeichen anzeigen
                log_data = json.loads(message['data'])
                
                if (log_data.get('type') == 'KILL' and 
                    log_data.get('weapon') in MELEE_WEAPONS):
                    process_melee_kill(log_data)
        
        time.sleep(0.01)
        
except KeyboardInterrupt:
    print("Melee-Kill VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    print("Erfolgreich beendet.")
