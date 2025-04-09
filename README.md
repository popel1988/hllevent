# Game Logs Processor

Ein System zur Verarbeitung von Spiellogs in Echtzeit, mit VIP-Belohnungen für Top-Spieler.

## Komponenten

- **Log Collector**: Sammelt Spiellogs von der API und sendet sie an Redis
- **VIP Rewards**: Belohnt die besten Spieler mit VIP-Status am Ende eines Spiels
- **Stats Tracker**: Verfolgt und analysiert Spielstatistiken (optional)

## Voraussetzungen

- Docker und Docker Compose
- Zugriffstoken für die Spiel-API

## Installation

1. Repository klonen:
git clone https://github.com/yourusername/game-logs-processor.git
cd game-logs-processor
2. API-Token in den Skripten konfigurieren (falls nicht bereits geschehen)

3. Mit Docker Compose starten:
docker-compose up -d
## Konfiguration

Die Services können über Umgebungsvariablen konfiguriert werden:

- `REDIS_HOST`: Hostname des Redis-Servers (Standard: "redis")
- `REDIS_PORT`: Port des Redis-Servers (Standard: 6379)

## Logs anzeigen

docker-compose logs -f
## Dienste stoppen

docker-compose down
## Entwicklung

Jeder Service kann unabhängig entwickelt und getestet werden. Nach Änderungen am Code:

docker-compose build <service_name>
docker-compose up -d <service_name>
undefined