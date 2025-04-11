
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

def get_current_vips():
    """Holt die aktuellen VIPs mit ihren Ablaufzeiten"""
    try:
        response = requests.get(f"{API_URL}/api/get_vip_ids", headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler beim Abrufen der VIP-Liste: {e}")
        return {}

    data = response.json()
    vips = {}
    for entry in data.get("result", []):
        if isinstance(entry, list) and len(entry) >= 2:
            player_id = entry[1]
            vip_data = entry[2] if len(entry) >=3 else {}
            if isinstance(vip_data, dict):
                expires = vip_data.get("vip_expiration")
                if expires and expires != "3000-01-01T00:00:00+00:00":
                    vips[player_id] = expires
    return vips

def grant_vip_status(player_id, player_name, kills, current_vips):
    """Gewährt VIP-Status nur wenn Restzeit <24h oder kein VIP vorhanden"""
    now = datetime.now(timezone.utc)
    
    # Prüfe bestehendes VIP
    if player_id in current_vips:
        try:
            expires_str = current_vips[player_id]
            expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00')).astimezone(timezone.utc)
            remaining = expires - now
            
            if remaining.total_seconds() > 86400:  # Mehr als 24h übrig
                logger.info(f"VIP für {player_name} läuft erst in {remaining} ab. Übersprungen.")
                return False
                
        except Exception as e:
            logger.error(f"Fehler bei VIP-Überprüfung für {player_name}: {e}")

    # Neues VIP gewähren
    expiration_time = now + timedelta(hours=24)
    
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

def reward_best_killers():
    """Identifiziert und belohnt die drei Spieler mit den meisten Kills"""
    scoreboard = get_scoreboard()
    if not scoreboard:
        logger.warning("Keine Spielerdaten im Scoreboard gefunden!")
        return

    current_vips = get_current_vips()  # Holt aktuelle VIPs vor der Verarbeitung

    sorted_players = sorted(
        scoreboard,
        key=lambda player: player.get("kills", 0),
        reverse=True
    )

    top_players = sorted_players[:3]

    logger.info("=== TOP 3 SPIELER ===")
    for idx, player in enumerate(top_players, 1):
        player_name = player.get("player", "Unbekannt")
        player_id = player.get("player_id")
        kills = player.get("kills", 0)

        logger.info(f"Platz {idx}: {player_name} | Kills: {kills} | ID: {player_id or 'Nicht gefunden'}")

        if not player_id:
            logger.warning(f"Spieler {player_name} konnte nicht belohnt werden (keine gültige ID).")
            continue

        if grant_vip_status(player_id, player_name, kills, current_vips):
            message = f"Gratulation an {player_name}! Mit {kills} Kills wurde VIP-Status für 24 Stunden gewährt!"
            send_server_message(message)

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
    """Identifiziert und belohnt die drei Spieler mit den meisten Kills"""
    scoreboard = get_scoreboard()
    if not scoreboard:
        logger.warning("Keine Spielerdaten im Scoreboard gefunden!")
        return

    # Sortiere alle Spieler basierend auf ihren Kills absteigend
    sorted_players = sorted(
        scoreboard,
        key=lambda player: player.get("kills", 0),
        reverse=True
    )

    # Nimm die besten 3 Spieler (oder weniger, falls weniger vorhanden)
    top_players = sorted_players[:3]

    logger.info("=== TOP 3 SPIELER ===")
    top_players_message = "Die besten 3 Spieler des Matches:\n"  # Nachricht für alle Spieler
    for idx, player in enumerate(top_players, 1):
        player_name = player.get("player", "Unbekannt")
        player_id = player.get("player_id")
        kills = player.get("kills", 0)

        logger.info(f"Platz {idx}: {player_name} | Kills: {kills} | ID: {player_id or 'Nicht gefunden'}")

        # Nachricht für die Zusammenfassung
        top_players_message += f"{idx}. {player_name} - {kills} Kills\n"

        # Individuelle VIP-Vergabe, falls Spieler-ID vorhanden
        if player_id:
            if grant_vip_status(player_id, player_name, kills):
                logger.info(f"VIP-Status an {player_name} vergeben.")
        else:
            logger.warning(f"Spieler {player_name} konnte nicht belohnt werden (keine gültige ID).")

    logger.info("=== ENDE DER TOP 3 LISTE ===")

    # Sende Nachricht mit den besten 3 Spielern an alle Spieler
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
