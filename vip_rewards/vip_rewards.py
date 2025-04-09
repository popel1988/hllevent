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

# Globale Variable zur Verfolgung des letzten Belohnungszeitpunkts
last_reward_time = 0
REWARD_COOLDOWN = 300  # 5 Minuten Abkühlzeit in Sekunden

def convert_utc_to_local(utc_time_str):
    """Konvertiert einen UTC-Zeitstempel in lokale Zeit (CEST)"""
    utc_time = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
    local_tz = pytz.timezone('Europe/Berlin')
    local_time = utc_time.astimezone(local_tz)
    return local_time.strftime('%Y-%m-%d %H:%M:%S %Z')

def get_scoreboard():
    """Ruft die aktuelle Anzeigetafel ab"""
    response = requests.get(f"{API_URL}/api/get_live_scoreboard", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print("API-Antwort erfolgreich abgerufen")
        return data.get("result", [])
    else:
        print(f"Fehler beim Abrufen der Anzeigetafel: {response.status_code}")
        return None

def find_best_killers(scoreboard_data):
    """Identifiziert den Spieler mit den meisten Kills"""
    if not scoreboard_data:
        return {"player": None, "kills": 0}
    
    best_killer = {"player": None, "kills": 0}
    
    for player in scoreboard_data:
        if isinstance(player, dict) and "kills" in player:
            kills = player.get("kills", 0)
            if kills > best_killer["kills"]:
                best_killer = {"player": player, "kills": kills}
    
    return best_killer

def grant_vip_status(player_id, player_name, kills):
    """Gewährt einem Spieler VIP-Status über die API"""
    data = {
        "player_id": player_id,
        "description": f"Belohnung für beste Leistung mit {kills} Kills",
        "expiration": "24h"
    }
    
    response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
    if response.status_code == 200:
        print(f"VIP-Status erfolgreich für {player_name} (ID: {player_id}) gewährt")
        return True
    else:
        print(f"Fehler beim Gewähren des VIP-Status: {response.status_code}, Antwort: {response.text}")
        return False

def get_player_ids():
    """Ruft alle aktuellen Spieler-IDs vom Server ab"""
    response = requests.get(f"{API_URL}/api/get_playerids?as_dict=True", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Spieler-IDs erfolgreich abgerufen: {len(data)} Spieler gefunden")
        return data
    else:
        print(f"Fehler beim Abrufen der Spieler-IDs: {response.status_code}")
        return {}

def message_player(player_id, message):
    """Sendet eine Nachricht an einen bestimmten Spieler"""
    data = {
        "player_id": player_id,
        "message": message,
        "by": "VIP Reward System",
        "save_message": True
    }
    
    response = requests.post(f"{API_URL}/api/message_player", headers=headers, json=data)
    if response.status_code == 200:
        return True
    else:
        print(f"Fehler beim Senden der Nachricht an Spieler {player_id}: {response.status_code}, Antwort: {response.text}")
        return False

def send_server_message(message):
    """Sendet eine Nachricht an alle Spieler auf dem Server"""
    players = get_player_ids()
    if not players:
        print("Keine Spieler gefunden, an die Nachrichten gesendet werden können")
        return False
    
    success_count = 0
    for player_id, player_name in players.items():
        if message_player(player_id, message):
            success_count += 1
    
    print(f"Nachricht an {success_count} von {len(players)} Spielern gesendet: {message}")
    return success_count > 0

def reward_best_killers():
    """Identifiziert und belohnt den Spieler mit den meisten Kills"""
    scoreboard = get_scoreboard()
    if not scoreboard:
        print("Konnte keine Spielerdaten abrufen.")
        return
    
    best_killer = find_best_killers(scoreboard)
    
    if best_killer["player"]:
        player = best_killer["player"]
        player_name = player.get("name", "Unbekannt")
        player_id = player.get("player_id")
        kills = best_killer["kills"]
        
        print(f"Bester Killer: {player_name} mit {kills} Kills")
        
        if player_id:
            if grant_vip_status(player_id, player_name, kills):
                message = f"Gratulation an {player_name}! Mit {kills} Kills wurde VIP-Status für 24 Stunden gewährt!"
                send_server_message(message)
        else:
            print(f"Konnte VIP-Status nicht gewähren: Keine Spieler-ID für {player_name}")
    else:
        print("Kein Spieler gefunden.")

def handle_match_ended_event(log_data):
    """Verarbeitet ein MATCH ENDED Event und belohnt die besten Spieler"""
    global last_reward_time
    current_time = time.time()
    
    server_id = log_data.get("server", "unknown")
    print(f"\n=== MATCH BEENDET AUF SERVER {server_id} ===")
    
    if current_time - last_reward_time < REWARD_COOLDOWN:
        print(f"Belohnung übersprungen. Nächste Belohnung möglich in {REWARD_COOLDOWN - (current_time - last_reward_time):.0f} Sekunden.")
        return
    
    print("Starte Belohnungsprozess für die besten Spieler...")
    
    try:
        reward_best_killers()
        print("Belohnungsprozess abgeschlossen.")
        last_reward_time = current_time
    except Exception as e:
        print(f"Fehler im Belohnungsprozess: {str(e)}")
        import traceback
        traceback.print_exc()

# Den game_logs Channel abonnieren
pubsub.subscribe('game_logs')
print(f"Erfolgreich 'game_logs' Channel abonniert auf {REDIS_HOST}:{REDIS_PORT}")

print("VIP-Belohnungs-Service gestartet. Warte auf MATCH ENDED Events...")

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
                
                if log_data.get('type') == 'MATCH ENDED':
                    local_time = convert_utc_to_local(log_data["event_time"])
                    print(f"MATCH ENDED Event erkannt: {local_time}")
                    handle_match_ended_event(log_data)
        
        time.sleep(0.01)
        
except KeyboardInterrupt:
    print("VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    print("Erfolgreich beendet.")
