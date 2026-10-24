#!/bin/sh
# Spielt eine Sicherung in eine Docker-Installation zurück.
# ACHTUNG: überschreibt Datenbank und Ablage.
# Aufruf: scripts/docker-wiederherstellen.sh /pfad/zur/sicherung/steuy-JJJJ-MM-TT_HHMMSS
# Funktioniert auch mit Sicherungen aus scripts/sicherung.sh und mit älteren Sicherungsordnern.
set -eu

QUELLE="${1:?Bitte Sicherungsordner angeben}"
if command -v sha256sum > /dev/null; then
    ( cd "$QUELLE" && sha256sum -c pruefsummen.txt )
else
    ( cd "$QUELLE" && shasum -a 256 -c pruefsummen.txt )
fi

docker compose stop app
docker compose exec -T db pg_restore --clean --if-exists --no-owner --username=steuy --dbname=steuy < "$QUELLE/datenbank.dump"
docker compose run --rm -T --no-deps app sh -c \
    'rm -rf /daten/ablage/* && tar -xzf - -C /daten' < "$QUELLE/ablage.tar.gz"
docker compose up -d app
echo "Wiederhergestellt aus $QUELLE"
