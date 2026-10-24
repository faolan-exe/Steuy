#!/bin/sh
# Sicherung einer Docker-Installation: Datenbank und Ablage in einen Ordner mit Zeitstempel.
# Auf dem Server im Projektordner ausführen: scripts/docker-sicherung.sh /pfad/zum/sicherungsordner
# Gleiches Format wie scripts/sicherung.sh, zurückspielen mit scripts/docker-wiederherstellen.sh.
set -eu

ZIEL="${1:?Bitte Zielordner angeben}"
ORDNER="$ZIEL/steuy-$(date +%Y-%m-%d_%H%M%S)"
mkdir -p "$ORDNER"

# pg_dump im Datenbank-Container, damit die Version zum Server passt
docker compose exec -T db pg_dump --format=custom --username=steuy steuy > "$ORDNER/datenbank.dump"
docker compose exec -T app tar -czf - -C /daten ablage > "$ORDNER/ablage.tar.gz"

if command -v sha256sum > /dev/null; then
    ( cd "$ORDNER" && sha256sum datenbank.dump ablage.tar.gz > pruefsummen.txt )
else
    ( cd "$ORDNER" && shasum -a 256 datenbank.dump ablage.tar.gz > pruefsummen.txt )
fi
echo "Sicherung fertig: $ORDNER"
