
#!/usr/bin/env python3
import redis
import json
import time
import requests
from datetime import datetime, timezone, timedelta
import pytz
from config import API_URL, API_KEY, REDIS_HOST, REDIS_PORT
import logging

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,  # Log-Level auf INFO setzen
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Standard-Output Stream aktivieren
)
logger = logging.getLogger(__name__)
logger.info("VIP Rewards Skript gestartet...")

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
    try:
        response = requests.get(f"{API_URL}/api/get_live_scoreboard", headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Abrufen der Anzeigetafel: {e}")
        return None

    data = response.json()
    stats = data.get("result", {}).get("stats", [])

    # Debug: Schreibe komplette Scoreboard-Daten in die Logs
    logger.info("=== ROHE SCOREBOARD-DATEN ===")
    logger.info(json.dumps(data, indent=2))
    logger.info("=============================")
     
    logger.info("=== SPIELERSTATISTIKEN ===")
    for player in stats[:10]:  # Zeige nur die ersten 10 Spieler an (falls umfangreich)
        logger.info(json.dumps(player, indent=2))
    logger.info("=========================")

    return stats

def grant_vip_status(player_id, player_name, kills):
    """Gewährt VIP-Status mit korrekter Zeitangabe"""
    expiration_time = datetime.now(timezone.utc) + timedelta(hours=24)
    data = {
        "player_id": player_id,
        "description": f"Top Killer mit {kills} Kills",
        "expiration": expiration_time.isoformat(timespec='milliseconds').replace("+00:00", "Z")
    }

    try:
        response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Setzen des VIP-Status: {e}")
        return False

    logger.info(f"VIP bis {expiration_time} für {player_name} gesetzt (ID: {player_id})")
    return True

def get_player_ids():
    """Ruft alle aktuellen Spieler-IDs vom Server ab"""
    try:
        response = requests.get(f"{API_URL}/api/get_playerids", headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Abrufen der Spieler-IDs: {e}")
        return []

    data = response.json()
    return data.get("result", [])

def message_player(player_id, message):
    """Sendet eine Nachricht an einen bestimmten Spieler"""
    data = {
        "player_id": player_id,
        "message": message,
        "by": "VIP Reward System",
        "save_message": True
    }

    try:
        response = requests.post(f"{API_URL}/api/message_player", headers=headers, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Senden der Nachricht an Spieler {player_id}: {e}")
        return False

    logger.info(f"Nachricht erfolgreich an Spieler {player_id} gesendet.")
    return True

def send_server_message(message):
    """Sendet eine Nachricht an alle Spieler auf dem Server"""
    players = get_player_ids()
    if not players:
        logger.warning("Keine Spieler gefunden, an die Nachrichten gesendet werden können.")
        return

    success_count = 0
    for player_entry in players:
        if isinstance(player_entry, list) and len(player_entry) > 1:
            player_name, player_id = player_entry
            logger.info(f"Nachricht wird an {player_name} gesendet (ID: {player_id})")
            if message_player(player_id, message):
                success_count += 1

    logger.info(f"Nachricht an {success_count}/{len(players)} Spieler gesendet: {message}")

def reward_best_killers():
    """Identifiziert und belohnt den Spieler mit den meisten Kills"""
    scoreboard = get_scoreboard()
    if not scoreboard:
        logger.warning("Keine Spielerdaten im Scoreboard gefunden!")
        return

    best_killer = {"name": None, "kills": 0, "id": None}

    for player in scoreboard:
        if isinstance(player, dict):
            kills = player.get("kills", 0)
            player_name = player.get("player", "Unbekannt")
            player_id = player.get("player_id")

            logger.info(f"Spieler: {player_name} | Kills: {kills} | ID: {player_id or 'Nicht gefunden'}")

            if kills > best_killer["kills"]:
                best_killer = {
                    "name": player_name,
                    "kills": kills,
                    "id": player_id
                }

    if not best_killer["id"]:
        logger.warning("Fehler: Kein gültiger Spieler mit Kills gefunden!")
        return

    logger.info(f"=== BESTER SPIELER ===\nName: {best_killer['name']} | Kills: {best_killer['kills']} | ID: {best_killer['id']}")
    if grant_vip_status(best_killer["id"], best_killer["name"], best_killer["kills"]):
        message = f"Gratulation an {best_killer['name']}! Mit {best_killer['kills']} Kills wurde VIP-Status für 24 Stunden gewährt!"
        send_server_message(message)

def handle_match_ended(log_data):
    """Verarbeitet ein MATCH ENDED Event und belohnt die besten Spieler"""
    global last_reward_time
    current_time = time.time()

    server_id = log_data.get("server", "unknown")
    logger.info(f"=== MATCH BEENDET AUF SERVER {server_id} ===")

    if current_time - last_reward_time < REWARD_COOLDOWN:
        logger.warning(f"Belohnung übersprungen. Nächste Belohnung möglich in {REWARD_COOLDOWN - (current_time - last_reward_time):.0f} Sekunden.")
        return

    try:
        reward_best_killers()
        logger.info("Belohnungsprozess abgeschlossen.")
        last_reward_time = current_time
    except Exception as e:
        logger.error(f"Fehler im Belohnungsprozess: {str(e)}")
        import traceback
        traceback.print_exc()

# Den game_logs Channel abonnieren
pubsub.subscribe('game_logs')
logger.info("VIP-Belohnungs-Service gestartet. Warte auf MATCH ENDED Events...")

try:
    while True:
        message = pubsub.get_message()
        if message and message['type'] == 'message':
            log_data = json.loads(message['data'])
            if log_data.get('type') == 'MATCH ENDED':
                handle_match_ended(log_data)
        time.sleep(0.01)
except KeyboardInterrupt:
    logger.info("VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    logger.info("Erfolgreich beendet.")
