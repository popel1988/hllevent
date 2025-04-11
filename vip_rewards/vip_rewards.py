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
    level=logging.INFO,
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

def get_current_vips():
    """Holt die aktuellen VIPs mit ihren Ablaufzeiten als datetime-Objekte"""
    try:
        response = requests.get(f"{API_URL}/api/get_vip_ids", headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Abrufen der VIP-Liste: {e}")
        return {}

    data = response.json()
    vips = {}

    for entry in data.get("result", []):
        player_id = entry.get("player_id")
        expires_str = entry.get("vip_expiration")
        
        if not player_id or not expires_str:
            continue
            
        # Ignoriere permanente VIPs
        if expires_str.startswith("3000-01-01"):
            continue
            
        try:
            expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00')).astimezone(timezone.utc)
            vips[player_id] = expires
        except Exception as e:
            logger.error(f"Fehler beim Parsen der VIP-Zeit für {player_id}: {e}")
            continue

    return vips

def grant_vip_status(player_id, player_name, kills, current_vips):
    """Gewährt 24h VIP-Zeit zusätzlich zur bestehenden VIP-Zeit (falls vorhanden)"""
    now = datetime.now(timezone.utc)
    
    # Bestehende Ablaufzeit holen oder None
    current_expiration = current_vips.get(player_id)
    
    if current_expiration and current_expiration > now:
        # Füge 24 Stunden zur bestehenden Zeit hinzu
        new_expiration = current_expiration + timedelta(hours=24)
        action_type = "verlängert"
    else:
        # Setze neue 24h VIP-Zeit
        new_expiration = now + timedelta(hours=24)
        action_type = "neu vergeben"

    data = {
        "player_id": player_id,
        "description": f"Top Killer mit {kills} Kills ({action_type})",
        "expiration": new_expiration.isoformat(timespec='milliseconds').replace("+00:00", "Z")
    }

    try:
        response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Setzen des VIP-Status: {e}")
        return False

    logger.info(f"VIP bis {new_expiration} für {player_name} {action_type} (ID: {player_id})")
    return True

def send_server_message(message):
    """Sendet eine Nachricht an alle Spieler auf dem Server"""
    try:
        # Spieler-IDs abrufen
        response = requests.get(f"{API_URL}/api/get_playerids", headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Abrufen der Spieler-IDs: {e}")
        return

    data = response.json()
    players = data.get("result", [])
    success_count = 0

    for player_entry in players:
        if isinstance(player_entry, list) and len(player_entry) > 1:
            player_name, player_id = player_entry
            # Nachricht an einzelne Spieler senden
            data = {
                "player_id": player_id,
                "message": message,
                "by": "VIP Belohnungssystem",
                "save_message": True
            }
            try:
                response = requests.post(f"{API_URL}/api/message_player", headers=headers, json=data)
                response.raise_for_status()
                success_count += 1
            except requests.exceptions.RequestException as e:
                logger.error(f"Fehler beim Senden der Nachricht an {player_name} (ID: {player_id}): {e}")

    logger.info(f"Nachricht an {success_count}/{len(players)} Spieler gesendet: {message[:50]}...")


def reward_best_killers():
    """Identifiziert und belohnt die drei Spieler mit den meisten Kills"""
    scoreboard = get_scoreboard()
    if not scoreboard:
        logger.warning("Keine Spielerdaten im Scoreboard gefunden!")
        return

    current_vips = get_current_vips()

    sorted_players = sorted(
        scoreboard,
        key=lambda player: player.get("kills", 0),
        reverse=True
    )

    top_players = sorted_players[:3]

    logger.info("=== TOP 3 SPIELER ===")
    top_players_message = "Die besten 3 Spieler des Matches:\n"
    for idx, player in enumerate(top_players, 1):
        player_name = player.get("player", "Unbekannt")
        player_id = player.get("player_id")
        kills = player.get("kills", 0)

        logger.info(f"Platz {idx}: {player_name} | Kills: {kills} | ID: {player_id or 'Nicht gefunden'}")

        if not player_id:
            logger.warning(f"Spieler {player_name} konnte nicht belohnt werden (keine gültige ID).")
            continue

        if grant_vip_status(player_id, player_name, kills, current_vips):
            top_players_message += f"{idx}. {player_name} - {kills} Kills\n"

    logger.info("=== ENDE DER TOP 3 LISTE ===")
    send_server_message(top_players_message)

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
