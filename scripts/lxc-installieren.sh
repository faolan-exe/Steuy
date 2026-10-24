#!/bin/sh
# Installiert steuy komplett in einem frischen Debian- oder Ubuntu-Container (z. B. Proxmox LXC).
# Als root im Container ausführen, danach die ausgegebene Adresse im Browser öffnen.
# Anleitung: docs/lxc.md
#
# Was passiert: Docker und nginx installieren, steuy holen, Zugangsdaten erzeugen,
# starten und prüfen. Das Skript ist wiederholbar (nützlich für Updates): Es überschreibt
# weder die .env noch die nginx-Einstellungen noch Daten.
#
# Eigene Quelle für den Code: REPO_URL=https://... sh lxc-installieren.sh
set -eu

REPO_URL="${REPO_URL:-https://github.com/faolan-exe/Steuy.git}"
ZIEL="${ZIEL:-/opt/steuy}"
export DEBIAN_FRONTEND=noninteractive

fehler() {
    echo >&2
    echo "FEHLER: $1" >&2
    exit 1
}

if [ "$(id -u)" -ne 0 ]; then
    fehler "Bitte als root ausführen (im Container ist das der Standard)."
fi

. /etc/os-release
case "${ID:-}" in
    debian | ubuntu) ;;
    *) fehler "Dieses Skript kennt nur Debian und Ubuntu, gefunden: ${ID:-unbekannt}." ;;
esac

echo "==> 1/5 Grundpakete und Webserver"
apt-get update -q
apt-get install -y -q ca-certificates curl git openssl nginx

docker_archiv_einrichten() {
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
}

if ! command -v docker > /dev/null 2>&1; then
    echo "==> 2/5 Docker aus dem offiziellen Docker-Paketarchiv"
    docker_archiv_einrichten
    apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
    echo "==> 2/5 Docker ist schon installiert"
fi

# Läuft Docker wirklich? In einem Container klappt das nur mit aktivierter Verschachtelung.
if ! docker info > /dev/null 2>&1; then
    systemctl start docker > /dev/null 2>&1 || true
    sleep 3
fi
if ! docker info > /dev/null 2>&1; then
    fehler "Docker startet nicht. Im Proxmox-Container unter Optionen → Features müssen
       \"Nesting\" und \"keyctl\" aktiviert sein. Danach den Container neu starten und dieses
       Skript noch einmal ausführen. Mehr dazu: docs/lxc.md, Abschnitt \"Wenn etwas nicht klappt\"."
fi

# Manche Docker-Installationen (z. B. aus den Ubuntu-Paketen) haben kein Compose-Plugin oder
# nur das veraltete Compose 1. steuy braucht "docker compose" in Version 2.
if ! docker compose version > /dev/null 2>&1; then
    echo "    Das Compose-Plugin fehlt und wird nachinstalliert."
    apt-get install -y -q docker-compose-v2 > /dev/null 2>&1 ||
        { docker_archiv_einrichten && apt-get install -y -q docker-compose-plugin; } ||
        fehler "Das Compose-Plugin konnte nicht installiert werden. Bitte \"docker-compose-plugin\"
       nach der Docker-Anleitung (docs.docker.com/engine/install) nachinstallieren."
fi
docker compose version > /dev/null 2>&1 || fehler "\"docker compose\" ist nicht verfügbar."

echo "==> 3/5 steuy nach $ZIEL holen"
if [ -d "$ZIEL/.git" ]; then
    git -C "$ZIEL" pull --ff-only
elif [ -f "$ZIEL/docker-compose.yml" ]; then
    echo "    Vorhandener Code in $ZIEL wird verwendet (kein Herunterladen)."
else
    git clone "$REPO_URL" "$ZIEL" ||
        fehler "Der Code konnte nicht heruntergeladen werden ($REPO_URL). Ist das Repository
       öffentlich? Sonst den Code von Hand nach $ZIEL kopieren (siehe docs/lxc.md)."
fi
cd "$ZIEL"
# Von macOS beim Packen erzeugte Metadaten-Dateien (._*) würden sonst als Programmcode gelesen
find . -name '._*' -not -path './.git/*' -delete

if [ ! -f .env ]; then
    umask 077
    # PROXY_ANZAHL=1: Hinter nginx kommt die Adresse des Besuchers aus dem Kopf der Anfrage.
    printf 'SECRET_KEY=%s\nPOSTGRES_PASSWORD=%s\nPROXY_ANZAHL=1\n' \
        "$(openssl rand -hex 32)" "$(openssl rand -hex 16)" > .env
    echo "    .env mit zufälligen Schlüsseln angelegt: $ZIEL/.env"
    echo "    Bitte den SECRET_KEY daraus im Passwortmanager sichern."
else
    echo "    Vorhandene .env bleibt unverändert."
fi

# Ordner und Dienst für das Update per Knopfdruck in den Einstellungen: Die App legt eine Anfrage
# in update/ ab, der Dienst führt scripts/update-ausfuehren.sh aus (als root, nur dieses Skript).
mkdir -p "$ZIEL/update"
chown 1000:1000 "$ZIEL/update"
cat > /etc/systemd/system/steuy-update.service << EOF
[Unit]
Description=steuy aktualisieren (Anfrage aus den Einstellungen)

[Service]
Type=oneshot
ExecStart=/bin/sh $ZIEL/scripts/update-ausfuehren.sh
EOF
cat > /etc/systemd/system/steuy-update.path << EOF
[Unit]
Description=steuy: wartet auf eine Update-Anfrage

[Path]
PathExists=$ZIEL/update/anfrage
Unit=steuy-update.service

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now steuy-update.path > /dev/null 2>&1 || true

echo "==> 4/5 steuy bauen und starten (beim ersten Mal einige Minuten)"
# BAKE aus: Sonst warnt Compose bei fehlendem buildx, obwohl das Bauen auch so klappt.
COMPOSE_BAKE=false docker compose up -d --build --wait ||
    fehler "steuy startet nicht. Die Meldungen zeigt: cd $ZIEL && docker compose logs"

echo "==> 5/5 Webserver einrichten"
SEITE=/etc/nginx/sites-available/steuy
if [ ! -f "$SEITE" ]; then
    cat > "$SEITE" << 'EOF'
# steuy: nginx leitet an die App im Container weiter (nur lokal auf Port 8000).
# HTTPS und eine Domain richtest du später mit certbot ein, siehe docs/lxc.md.
server {
    listen 80 default_server;
    server_name _;

    # Belege hochladen: steuy erlaubt bis zu 100 MB pro Anfrage
    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF
    rm -f /etc/nginx/sites-enabled/default
    ln -sf "$SEITE" /etc/nginx/sites-enabled/steuy
else
    echo "    Vorhandene nginx-Einstellung bleibt unverändert."
fi
nginx -t > /dev/null 2>&1 || fehler "Die nginx-Einstellung ist fehlerhaft. Prüfen mit: nginx -t"
systemctl enable nginx > /dev/null 2>&1 || true
systemctl restart nginx

# Erreichbar? Dann ist die ganze Kette in Ordnung: nginx, App, Datenbank.
ok=""
for versuch in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS http://127.0.0.1/gesund > /dev/null 2>&1; then
        ok=ja
        break
    fi
    sleep 2
done
[ -n "$ok" ] || fehler "steuy antwortet nicht über nginx. Prüfen mit: cd $ZIEL && docker compose ps"

# Adresse der echten Netzwerkkarte (über die Standardroute). "hostname -I" wäre falsch, weil es
# auch die Docker-Netze (172.x.x.x) aufzählt, oft sogar zuerst.
ADRESSE="$(ip -4 route get 1.1.1.1 2> /dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
[ -n "$ADRESSE" ] || ADRESSE="$(hostname -I 2> /dev/null | awk '{print $1}')"
echo
echo "=============================================================="
echo " Fertig! steuy läuft."
echo
echo "   Öffne im Browser:   http://${ADRESSE:-<IP-des-Containers>}"
echo
echo " Dort startet der Einrichtungsassistent."
echo " Wichtig: Diese Verbindung ist nicht verschlüsselt. Nutze sie nur"
echo " in deinem eigenen Netzwerk. Für den Zugriff von unterwegs: docs/lxc.md"
echo "=============================================================="
