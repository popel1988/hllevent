#!/usr/bin/env python3
import redis
import json
import time
import requests
from datetime import datetime, timezone, timedelta
import pytz
from collections import defaultdict
from config import API_URL, API_KEY, REDIS_HOST, REDIS_PORT

# Redis-Verbindung
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
pubsub = r.pubsub()

# API-Konfiguration
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Globale Variable zur Verfolgung des letzten Belohnungszeitpunkts
last_reward_time = 0
REWARD_COOLDOWN = 300  # 5 Minuten Abkühlzeit in Sekunden

# Match-Statistiken
current_match = {
    "server": None,
    "start_time": None,
    "kills": defaultdict(int),
    "deaths": defaultdict(int)
}

def reset_match_stats():
    """Setzt die Statistiken für ein neues Match zurück"""
    current_match["kills"].clear()
    current_match["deaths"].clear()
    print("=== MATCH STATISTIKEN ZURÜCKGESETT ===")

def convert_utc_to_local(utc_time_str):
    """Konvertiert einen UTC-Zeitstempel in lokale Zeit (CEST)"""
    utc_time = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
    local_tz = pytz.timezone('Europe/Berlin')
    local_time = utc_time.astimezone(local_tz)
    return local_time.strftime('%Y-%m-%d %H:%M:%S %Z')

def get_scoreboard():
    response = requests.get(f"{API_URL}/api/get_live_scoreboard", headers=headers)
    if response.status_code != 200:
        return None

    data = response.json()
    
    # Debug-Log des kompletten API-Response
    print("Scoreboard Rohdaten:", json.dumps(data, indent=2))
    
    # Extrahiere Spielerliste aus der verschachtelten Struktur
    players = data.get("result", {}).get("stats", [])
    
    if not players:
        print("Keine Spielerdaten im Scoreboard gefunden")
        return None
    
    print(f"Gefundene Spieler: {len(players)}")
    return players

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
        print(f"VIP bis {expiration_time} für {player_name} gesetzt")
        return True
    else:
        print(f"API Fehler: {response.status_code} - {response.text}")
        return False

def reward_best_killers():
    scoreboard = get_scoreboard()
    if not scoreboard:
        return

    best_killer = {"player": None, "kills": 0}
    
    for player in scoreboard:
        if isinstance(player, dict):
            kills = player.get("kills", 0)
            if kills > best_killer["kills"]:
                best_killer = {
                    "player": player,
                    "kills": kills,
                    "name": player.get("player", "Unbekannt"),
                    "id": player.get("steam_id_64")
                }
    
    if best_killer["id"]:
        print(f"Bester Spieler: {best_killer['name']} ({best_killer['kills']} Kills)")
        grant_vip_status(best_killer["id"], best_killer["name"], best_killer["kills"])
    else:
        print("Kein gültiger Top-Spieler gefunden")

def handle_match_ended(log_data):
    global last_reward_time, current_match
    current_time = time.time()
    
    server_id = log_data.get("server", "unknown")
    print(f"\n=== MATCH BEENDET AUF SERVER {server_id} ===")
    
    if current_time - last_reward_time < REWARD_COOLDOWN:
        print(f"Belohnung übersprungen. Nächste Belohnung möglich in {REWARD_COOLDOWN - (current_time - last_reward_time):.0f} Sekunden.")
        return
    
    # Statistiken vor der Belohnung zurücksetzen
    reset_match_stats()
    
    try:
        reward_best_killers()
        print("Belohnungsprozess abgeschlossen.")
        last_reward_time = current_time
    except Exception as e:
        print(f"Fehler im Belohnungsprozess: {str(e)}")
        traceback.print_exc()
    
    # Sofortige Zurücksetzung der Stats nach der Belohnung
    reset_match_stats()

# Den game_logs Channel abonnieren
pubsub.subscribe('game_logs')

print("VIP-Belohnungs-Service gestartet. Warte auf MATCH ENDED Events...")

# Nachricht zum Überspringen der Bestätigungsnachricht
pubsub.get_message()

try:
    while True:
        message = pubsub.get_message()
        
        if message and message['type'] == 'message':
            log_data = json.loads(message['data'])
            
            if log_data.get('type') == 'MATCH ENDED':
                local_time = convert_utc_to_local(log_data["event_time"])
                print(f"MATCH ENDED Event erkannt: {local_time}")
                handle_match_ended(log_data)
        
        time.sleep(0.01)
        
except KeyboardInterrupt:
    print("VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    print("Erfolgreich beendet.")
