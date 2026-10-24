#!/bin/sh
# Stellt eine Sicherung aus scripts/sicherung.sh wieder her.
# ACHTUNG: überschreibt die Datenbank und die Ablage.
# Aufruf: scripts/wiederherstellen.sh /pfad/zur/sicherung/steuy-JJJJ-MM-TT_HHMMSS
set -eu

QUELLE="${1:?Bitte Sicherungsordner angeben}"
DB_URL="$(printf '%s' "${DATABASE_URL:?DATABASE_URL fehlt}" | sed 's/+psycopg//')"
ABLAGE="${ABLAGE_VERZEICHNIS:-instance/ablage}"

( cd "$QUELLE" && shasum -a 256 -c pruefsummen.txt )
pg_restore --clean --if-exists --no-owner --dbname="$DB_URL" "$QUELLE/datenbank.dump"
mkdir -p "$(dirname "$ABLAGE")"
rm -rf "$ABLAGE"
tar -xzf "$QUELLE/ablage.tar.gz" -C "$(dirname "$ABLAGE")"
echo "Wiederhergestellt aus $QUELLE"
