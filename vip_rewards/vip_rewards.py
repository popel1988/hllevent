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
    if response.status_code != 200:
        print(f"Fehler beim Abrufen der Anzeigetafel: {response.status_code}")
        return None

    data = response.json()
    
    # Debug: Schreibe komplette Scoreboard-Daten in die Logs
    print("=== ROHE SCOREBOARD-DATEN ===")
    print(json.dumps(data, indent=2))
    print("=============================")
    
    stats = data.get("result", {}).get("stats", [])
    return stats

def grant_vip_status(player_id, player_name, kills):
    """Gewährt VIP-Status mit korrekter Zeitangabe"""
    expiration_time = datetime.now(timezone.utc) + timedelta(hours=24)
    
    data = {
        "player_id": player_id,
        "description": f"Top Killer mit {kills} Kills",
        "expiration": expiration_time.isoformat(timespec='milliseconds').replace("+00:00", "Z")
    }
    
    response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
    
    if response.status_code == 200:
        print(f"VIP bis {expiration_time} für {player_name} gesetzt (ID: {player_id})")
        return True
    else:
        print(f"API Fehler: {response.status_code} - {response.text}")
        return False

def get_player_ids():
    """Ruft alle aktuellen Spieler-IDs vom Server ab"""
    response = requests.get(f"{API_URL}/api/get_playerids", headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("result", [])
    else:
        print(f"Fehler beim Abrufen der Spieler-IDs: {response.status_code}")
        return []

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
        print(f"Nachricht erfolgreich an Spieler {player_id} gesendet.")
        return True
    else:
        print(f"Fehler beim Senden der Nachricht an Spieler {player_id}: {response.status_code}, Antwort: {response.text}")
        return False

def send_server_message(message):
    """Sendet eine Nachricht an alle Spieler auf dem Server"""
    players = get_player_ids()
    if not players:
        print("Keine Spieler gefunden, an die Nachrichten gesendet werden können.")
        return

    success_count = 0
    for player_entry in players:
        if isinstance(player_entry, list) and len(player_entry) > 1:
            player_name, player_id = player_entry  # Extrahiere Name und ID
            if message_player(player_id, message):
                success_count += 1

    print(f"Nachricht an {success_count} Spieler gesendet: {message}")

def reward_best_killers():
    """Identifiziert und belohnt den Spieler mit den meisten Kills"""
    scoreboard = get_scoreboard()
    if not scoreboard:
        return

    best_killer = {"player": None, "kills": 0}
    
    # Debug: Liste aller Spieler und ihrer Kills
    print("=== SPIELERSTATISTIKEN ===")
    for idx, player in enumerate(scoreboard, 1):
        if isinstance(player, dict):
            kills = player.get("kills", 0)
            player_name = player.get("player", "Unbekannt")
            player_id = player.get("player_id")
            print(f"Spieler {idx}: {player_name} | Kills: {kills} | ID: {player_id}")
    
    for player in scoreboard:
        if isinstance(player, dict):
            kills = player.get("kills", 0)
            if kills > best_killer["kills"]:
                best_killer = {
                    "player": player.get("player", "Unbekannt"),
                    "kills": kills,
                    "id": player.get("player_id")
                }
    
    print(f"=== BESTER SPIELER GEFUNDEN ===")
    print(f"Name: {best_killer['player']}")
    print(f"Kills: {best_killer['kills']}")
    print(f"ID: {best_killer['id']}")
    print("===============================")
    
    if best_killer["id"]:
        grant_vip_status(best_killer["id"], best_killer["player"], best_killer["kills"])
    else:
        print("Fehler: Keine gültige Spieler-ID gefunden")

def handle_match_ended(log_data):
    """Verarbeitet ein MATCH ENDED Event und belohnt die besten Spieler"""
    global last_reward_time
    current_time = time.time()
    
    server_id = log_data.get("server", "unknown")
    print(f"\n=== MATCH BEENDET AUF SERVER {server_id} ===")
    
    if current_time - last_reward_time < REWARD_COOLDOWN:
        print(f"Belohnung übersprungen. Nächste Belohnung möglich in {REWARD_COOLDOWN - (current_time - last_reward_time):.0f} Sekunden.")
        return

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

print("VIP-Belohnungs-Service gestartet. Warte auf MATCH ENDED Events...")

try:
    while True:
        message = pubsub.get_message()
        if message and message['type'] == 'message':
            log_data = json.loads(message['data'])
            if log_data.get('type') == 'MATCH ENDED':
                handle_match_ended(log_data)
        time.sleep(0.01)
except KeyboardInterrupt:
    print("VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    print("Erfolgreich beendet.")
