#!/bin/sh
# Richtet das Update per Knopfdruck ein (Einstellungen → Update), für jede Installation mit
# Docker Compose auf Linux mit systemd. Einmalig als root im Ordner von steuy ausführen:
#   sh scripts/update-dienst-einrichten.sh
# Das Installationsskript (lxc-installieren.sh) ruft es selbst auf.
#
# Ablauf beim Update: Die App legt nach deiner Bestätigung eine Anfrage in update/ ab. Ein
# systemd-Pfad bemerkt sie und startet scripts/update-ausfuehren.sh als root (nur dieses
# Skript): Sicherung, neue Version laden, bauen, prüfen, bei Fehlern zurück zur alten Version.
set -eu

ZIEL="${ZIEL:-$(cd "$(dirname "$0")/.." && pwd)}"

if [ "$(id -u)" -ne 0 ]; then
    echo "FEHLER: Bitte als root ausführen (z. B. mit sudo)." >&2
    exit 1
fi
if ! command -v systemctl > /dev/null 2>&1; then
    echo "FEHLER: systemd fehlt. Update dann von Hand: git pull && docker compose up -d --build" >&2
    exit 1
fi
[ -f "$ZIEL/docker-compose.yml" ] || {
    echo "FEHLER: $ZIEL ist kein steuy-Ordner (docker-compose.yml fehlt)." >&2
    exit 1
}

# Nur dieser Ordner ist für die App (Nutzer 1000 im Container) beschreibbar
mkdir -p "$ZIEL/update"
chown 1000:1000 "$ZIEL/update"
chmod 755 "$ZIEL/update"

cat > /etc/systemd/system/steuy-update.service << DIENST
[Unit]
Description=steuy aktualisieren (Anfrage aus den Einstellungen)

[Service]
Type=oneshot
Environment=ZIEL=$ZIEL
ExecStart=/bin/sh $ZIEL/scripts/update-ausfuehren.sh
DIENST
cat > /etc/systemd/system/steuy-update.path << PFAD
[Unit]
Description=steuy: wartet auf eine Update-Anfrage

[Path]
PathExists=$ZIEL/update/anfrage
Unit=steuy-update.service

[Install]
WantedBy=multi-user.target
PFAD
systemctl daemon-reload
systemctl enable --now steuy-update.path > /dev/null 2>&1 || true
echo "Update per Knopfdruck eingerichtet (Einstellungen → Update)."
