#!/bin/sh
# Sichert Datenbank und Ablage gemeinsam in ein Verzeichnis mit Zeitstempel.
# Aufruf: scripts/sicherung.sh /pfad/zum/sicherungsordner
# Erwartet DATABASE_URL und ABLAGE_VERZEICHNIS (z. B. aus der .env).
set -eu

ZIEL="${1:?Bitte Zielordner angeben}"
ZEIT="$(date +%Y-%m-%d_%H%M%S)"
ORDNER="$ZIEL/steuy-$ZEIT"
DB_URL="$(printf '%s' "${DATABASE_URL:?DATABASE_URL fehlt}" | sed 's/+psycopg//')"
ABLAGE="${ABLAGE_VERZEICHNIS:-instance/ablage}"

mkdir -p "$ORDNER"
pg_dump --format=custom --file="$ORDNER/datenbank.dump" "$DB_URL"
tar -czf "$ORDNER/ablage.tar.gz" -C "$(dirname "$ABLAGE")" "$(basename "$ABLAGE")"
( cd "$ORDNER" && shasum -a 256 datenbank.dump ablage.tar.gz > pruefsummen.txt )
echo "Sicherung fertig: $ORDNER"
