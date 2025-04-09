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

# Globale Variable zur Verfolgung des letzten Belohnungszeitpunkts
last_reward_time = 0
REWARD_COOLDOWN = 300  # 5 Minuten Abkühlzeit in Sekunden

def determine_platform(player_id):
    """Bestimmt die Plattform basierend auf der ID oder dem Format"""
    if not player_id:
        return "unknown"
        
    if isinstance(player_id, str):
        # Steam IDs sind typischerweise 17-stellige Zahlen
        if player_id.isdigit() and len(player_id) == 17:
            return "steam"
            
        # Epic Games IDs sind 32-stellige Hex-Strings
        if len(player_id) == 32 and all(c in "0123456789abcdef" for c in player_id.lower()):
            return "epic"
            
        # Xbox Live IDs haben oft ein bestimmtes Format
        if player_id.startswith("xbl_") or "xbox" in player_id.lower():
            return "xbox"
    
    # Standardfall, wenn keine spezifische Erkennung möglich ist
    return "unknown"

def get_scoreboard():
    """Ruft die aktuelle Anzeigetafel ab"""
    response = requests.get(f"{API_URL}/api/get_live_scoreboard", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print("API-Antwort erfolgreich abgerufen")
        
        # Debug-Ausgabe der Struktur
        print(f"Typ der Antwort: {type(data)}")
        print(f"Schlüssel im Dictionary: {list(data.keys())}")
        
        # Prüfen, ob 'result' im Dictionary vorhanden ist
        if "result" in data:
            result = data["result"]
            print(f"Typ des Results: {type(result)}")
            
            # Wenn result eine Liste ist, gib sie zurück
            if isinstance(result, list):
                print(f"Anzahl der Spieler im Result: {len(result)}")
                return result
            
            # Wenn result ein Dictionary ist, suche nach Spielerlisten
            elif isinstance(result, dict):
                print(f"Schlüssel im Result: {list(result.keys())}")
                
                # Versuche verschiedene mögliche Schlüssel
                for key in result.keys():
                    if isinstance(result[key], list) and result[key]:
                        print(f"Liste gefunden unter Schlüssel: {key} mit {len(result[key])} Elementen")
                        return result[key]
        
        return data
    else:
        print(f"Fehler beim Abrufen der Anzeigetafel: {response.status_code}")
        return None

def find_best_killers(scoreboard_data):
    """Identifiziert den Spieler mit den meisten Kills"""
    if not scoreboard_data:
        return {"player": None, "kills": 0}
    
    best_killer = {"player": None, "kills": 0}
    
    # Wenn scoreboard_data ein Dictionary ist
    if isinstance(scoreboard_data, dict):
        # Versuche, die Spieler unter 'result' zu finden
        if "result" in scoreboard_data and isinstance(scoreboard_data["result"], list):
            for player in scoreboard_data["result"]:
                if isinstance(player, dict) and "kills" in player:
                    kills = player.get("kills", 0)
                    if kills > best_killer["kills"]:
                        # Stelle sicher, dass wir die richtige ID basierend auf der Plattform bekommen
                        player_id = get_player_id_from_data(player)
                        if player_id:
                            player["player_id"] = player_id  # ID speichern für spätere Verwendung
                            best_killer = {"player": player, "kills": kills}
        else:
            # Durchsuche alle Schlüssel nach Listen
            for key, value in scoreboard_data.items():
                if isinstance(value, list):
                    for player in value:
                        if isinstance(player, dict) and "kills" in player:
                            kills = player.get("kills", 0)
                            if kills > best_killer["kills"]:
                                player_id = get_player_id_from_data(player)
                                if player_id:
                                    player["player_id"] = player_id
                                    best_killer = {"player": player, "kills": kills}
    
    # Wenn scoreboard_data eine Liste ist
    elif isinstance(scoreboard_data, list):
        for player in scoreboard_data:
            if isinstance(player, dict) and "kills" in player:
                kills = player.get("kills", 0)
                if kills > best_killer["kills"]:
                    player_id = get_player_id_from_data(player)
                    if player_id:
                        player["player_id"] = player_id
                        best_killer = {"player": player, "kills": kills}
    
    return best_killer

def get_player_id_from_data(player_data):
    """Extrahiert die Spieler-ID basierend auf verfügbaren Feldern und Plattform"""
    # Versuche verschiedene mögliche Felder für die ID
    id_fields = ["player_id", "steam_id_64", "epic_id", "xbox_id", "id"]
    
    for field in id_fields:
        if field in player_data and player_data[field]:
            return player_data[field]
    
    return None

def grant_vip_status(player_id, player_name, kills):
    """Gewährt einem Spieler VIP-Status über die API"""
    platform = determine_platform(player_id)
    
    data = {
        "player_id": player_id,
        "description": f"Belohnung für beste Leistung mit {kills} Kills",
        "expiration": "24h",  # 24 Stunden als String formatiert
        "platform": platform
    }
    
    response = requests.post(f"{API_URL}/api/add_vip", headers=headers, json=data)
    if response.status_code == 200:
        print(f"VIP-Status erfolgreich für {player_name} (ID: {player_id}, Plattform: {platform}) gewährt")
        return True
    else:
        print(f"Fehler beim Gewähren des VIP-Status: {response.status_code}, Antwort: {response.text}")
        return False

def get_player_ids():
    """Ruft alle aktuellen Spieler-IDs vom Server ab"""
    # Parameter as_dict=True hinzufügen, um ein Dictionary zurückzubekommen
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
    platform = determine_platform(player_id)
    
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
    # Alle Spieler-IDs abrufen
    players = get_player_ids()
    if not players:
        print("Keine Spieler gefunden, an die Nachrichten gesendet werden können")
        return False
    
    success_count = 0
    # Jedem Spieler einzeln eine Nachricht senden
    for player_id, player_name in players.items():
        if message_player(player_id, message):
            success_count += 1
    
    print(f"Nachricht an {success_count} von {len(players)} Spielern gesendet: {message}")
    return success_count > 0

def reward_best_killers():
    """Identifiziert und belohnt den Spieler mit den meisten Kills"""
    # Anzeigetafel abrufen
    scoreboard = get_scoreboard()
    if not scoreboard:
        print("Konnte keine Spielerdaten abrufen.")
        return
    
    # Besten Killer finden
    best_killer = find_best_killers(scoreboard)
    
    if best_killer["player"]:
        player = best_killer["player"]
        # Prüfen, ob "player" ein String oder ein Dictionary mit "name" ist
        if isinstance(player, dict):
            player_name = player.get("player", player.get("name", "Unbekannt"))
            player_id = player.get("player_id")
        else:
            print(f"Unerwartetes Spielerformat: {type(player)}")
            return
            
        kills = best_killer["kills"]
        
        print(f"Bester Killer: {player_name} mit {kills} Kills")
        
        if player_id:
            # VIP-Status gewähren
            if grant_vip_status(player_id, player_name, kills):
                # Servernachricht senden
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
    
    # Überprüfen, ob genug Zeit seit der letzten Belohnung vergangen ist
    if current_time - last_reward_time < REWARD_COOLDOWN:
        print(f"Belohnung übersprungen. Nächste Belohnung möglich in {REWARD_COOLDOWN - (current_time - last_reward_time):.0f} Sekunden.")
        return
    
    print("Starte Belohnungsprozess für die besten Spieler...")
    
    try:
        # Belohne die besten Spieler
        reward_best_killers()
        print("Belohnungsprozess abgeschlossen.")
        
        # Aktualisiere den Zeitpunkt der letzten Belohnung
        last_reward_time = current_time
    except Exception as e:
        print(f"Fehler im Belohnungsprozess: {str(e)}")
        import traceback
        traceback.print_exc()

# Den game_logs Channel abonnieren
pubsub.subscribe('game_logs')

print("VIP-Belohnungs-Service gestartet. Warte auf MATCH ENDED Events...")

# Nachricht zum Überspringen der Bestätigungsnachricht
pubsub.get_message()

try:
    while True:
        # Auf neue Nachrichten warten
        message = pubsub.get_message()
        
        if message and message['type'] == 'message':
            # Nachricht von bytes in JSON umwandeln
            log_data = json.loads(message['data'])
            
            # Nur auf MATCH ENDED Events reagieren
            if log_data.get('type') == 'MATCH ENDED':
                print(f"MATCH ENDED Event erkannt: {log_data}")
                handle_match_ended_event(log_data)
        
        # Kurze Pause, um CPU-Last zu reduzieren
        time.sleep(0.01)
        
except KeyboardInterrupt:
    print("VIP-Belohnungs-Service wird beendet...")
    pubsub.unsubscribe('game_logs')
    print("Erfolgreich beendet.")
