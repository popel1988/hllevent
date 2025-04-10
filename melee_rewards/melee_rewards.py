#!/usr/bin/env python3
import redis
import json
import time
import requests
from datetime import datetime, timezone, timedelta
import pytz
from config import API_URL, API_KEY, REDIS_HOST, REDIS_PORT
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
logger.info("Skript gestartet...")

# Redis-Verbindung
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
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
    expiration_time = datetime.now(timezone.utc) + timedelta(hours=VIP_DURATION_HOURS)
    
    data = {
        "player_id": player_id,
        "description": f"Belohnung für einen Kill mit {weapon}",
        "expiration": expiration_time.isoformat(timespec='milliseconds').replace("+00:00", "Z")
    }
    
    response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
    
    if response.status_code == 200:
        print(f"VIP bis {expiration_time} für {player_name} gesetzt")
        return True
    else:
        print(f"Fehler beim Setzen des VIP-Status: {response.status_code}, Antwort: {response.text}")
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
        print(f"Nachricht erfolgreich an {player_id} gesendet")
        return True
    else:
        print(f"Fehler beim Senden der Nachricht an Spieler {player_id}: {response.status_code}, Antwort: {response.text}")
        return False

def process_melee_kill(log_data):
    """Verarbeitet einen Melee-Kill und belohnt den Spieler"""
    killer_name = log_data.get("player1_name")
    killer_id = log_data.get("player1_id")
    victim_name = log_data.get("player2_name")
    weapon = log_data.get("weapon")
    event_time = log_data.get("event_time")
    
    if not killer_name or not killer_id or not weapon:
        print("Ungültige Melee-Kill-Daten, überspringen...")
        return
    
    local_time = convert_utc_to_local(event_time)
    print(f"\n=== MELEE KILL ERKANNT: {local_time} ===")
    print(f"{killer_name} hat {victim_name} mit {weapon} getötet!")
    
    # Gewährt VIP-Status und sendet eine Nachricht
    if grant_vip_status(killer_id, killer_name, weapon):
        message = f"Gratulation! Du hast {victim_name} mit {weapon} eliminiert und erhältst {VIP_DURATION_HOURS} Stunden VIP-Status!"
        message_player(killer_id, message)
        print(f"VIP-Status und Nachricht für {killer_name} verarbeitet.")

# Den game_logs Channel abonnieren
pubsub.subscribe('game_logs')

print("Melee-Kill VIP-Belohnungs-Service gestartet. Warte auf KILL-Events...")

# Nachricht zum Überspringen der Bestätigungsnachricht
pubsub.get_message()

try:
    while True:
        message = pubsub.get_message()
        
        if message and message['type'] == 'message':
            log_data = json.loads(message['data'])
            
            # Nur auf KILL-Events mit Melee-Waffen reagieren
            if (log_data.get('type') == 'KILL' and 
                log_data.get('weapon') in MELEE_WEAPONS):
                process_melee_kill(log_data)
        
        time.sleep(0.01)
        
except KeyboardInterrupt:
    print("Melee-Kill VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    print("Erfolgreich beendet.")
