#!/usr/bin/env python3
import redis
import json
import time
import requests
from datetime import datetime
from config import API_URL, API_KEY, REDIS_HOST, REDIS_PORT

# Redis-Verbindung
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
pubsub = r.pubsub()

# API-Konfiguration
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Melee-Waffen Liste
MELEE_WEAPONS = ["M3 Knife", "Feldspaten"]

# VIP-Belohnungsdauer in Stunden
VIP_DURATION_HOURS = 24  # 1 Tag

def grant_vip_status(player_id, player_name, weapon):
    """Gewährt einem Spieler VIP-Status über die API"""
    data = {
        "player_id": player_id,
        "description": f"Belohnung für einen Kill mit {weapon}",
        "expiration": "24h"  # 24 Stunden als String formatiert
    }
    
    response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
    if response.status_code == 200:
        print(f"VIP-Status erfolgreich für {player_name} (ID: {player_id}) gewährt")
        return True
    else:
        print(f"Fehler beim Gewähren des VIP-Status: {response.status_code}, Antwort: {response.text}")
        return False

def message_player(steam_id, message):
    """Sendet eine Nachricht an einen bestimmten Spieler"""
    data = {
        "steam_id_64": steam_id,
        "message": message
    }
    
    response = requests.post(f"{API_URL}/api/message_player", headers=headers, json=data)
    if response.status_code == 200:
        print(f"Nachricht erfolgreich an Spieler {steam_id} gesendet")
        return True
    else:
        print(f"Fehler beim Senden der Nachricht an Spieler {steam_id}: {response.status_code}, Antwort: {response.text}")
        return False

def process_melee_kill(log_data):
    """Verarbeitet einen Melee-Kill und belohnt den Spieler"""
    killer_name = log_data["player1_name"]
    killer_id = log_data["player1_id"]
    victim_name = log_data["player2_name"]
    weapon = log_data["weapon"]
    
    print(f"\n=== MELEE KILL ERKANNT ===")
    print(f"{killer_name} hat {victim_name} mit {weapon} getötet!")
    
    # VIP-Status gewähren
    if grant_vip_status(killer_id, killer_name, weapon):
        # Persönliche Nachricht an den Spieler senden
        message = f"Gratulation! Du hast {victim_name} mit {weapon} eliminiert und erhältst 24 Stunden VIP-Status!"
        message_player(killer_id, message)
        print(f"VIP-Status und Benachrichtigung für {killer_name} verarbeitet.")

# Den game_logs Channel abonnieren
pubsub.subscribe('game_logs')

print("Melee-Kill VIP-Belohnungs-Service gestartet. Warte auf Kill-Events...")

# Nachricht zum Überspringen der Bestätigungsnachricht
pubsub.get_message()

try:
    while True:
        # Auf neue Nachrichten warten
        message = pubsub.get_message()
        
        if message and message['type'] == 'message':
            # Nachricht von bytes in JSON umwandeln
            log_data = json.loads(message['data'])
            
            # Nur auf KILL-Events mit Melee-Waffen reagieren
            if (log_data.get('type') == 'KILL' and 
                log_data.get('weapon') in MELEE_WEAPONS):
                process_melee_kill(log_data)
        
        # Kurze Pause, um CPU-Last zu reduzieren
        time.sleep(0.01)
        
except KeyboardInterrupt:
    print("Melee-Kill VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    print("Erfolgreich beendet.")
