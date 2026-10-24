#!/bin/sh
# Führt ein Update aus, das die App in den Ordner update/ angefragt hat.
# Läuft als root über den systemd-Dienst steuy-update (eingerichtet von lxc-installieren.sh).
# Ablauf: sichern, neue Version laden und prüfen, Code ersetzen, neu bauen, prüfen.
# Klappt etwas nicht, wird der alte Code wiederhergestellt: die Daten bleiben unberührt.
#
# Zum Testen: UPDATE_QUELLE=/pfad/zu/version.tar.gz nimmt eine lokale Datei statt GitHub.
set -u

ZIEL="${ZIEL:-/opt/steuy}"
UPDATE="$ZIEL/update"
STATUS="$UPDATE/status.json"
SICHERUNG="${SICHERUNG:-/var/backups/steuy}"
ARBEIT="$(mktemp -d /tmp/steuy-update.XXXXXX)"
trap 'rm -rf "$ARBEIT"' EXIT

cd "$ZIEL" || exit 1

setze_status() { # Zustand, Schritt, Meldung
    printf '{"zustand":"%s","version":"%s","von":"%s","schritt":"%s","meldung":"%s"}\n' \
        "$1" "${TAG:-}" "${VON:-}" "$2" "$3" > "$UPDATE/status.tmp"
    chmod 644 "$UPDATE/status.tmp"
    chown 1000:1000 "$UPDATE/status.tmp" 2> /dev/null || true
    mv -f "$UPDATE/status.tmp" "$STATUS"
}

scheitern() { # Meldung
    echo "FEHLER: $1" >&2
    setze_status fehlgeschlagen "" "$1"
    exit 1
}

[ -f "$UPDATE/anfrage" ] || exit 0
TAG="$(sed -n 's/.*"version" *: *"\([^"]*\)".*/\1/p' "$UPDATE/anfrage")"
rm -f "$UPDATE/anfrage"
printf '%s' "$TAG" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' || scheitern "Ungültige Version in der Anfrage."
VON="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' app/version.py 2> /dev/null)"

# Einstellungen aus der .env (nur diese beiden Werte)
wert() { sed -n "s/^$1=//p" .env 2> /dev/null | tail -n 1; }
REPO="$(wert UPDATE_REPO)"
REPO="${REPO:-faolan-exe/Steuy}"
TOKEN="$(wert UPDATE_TOKEN)"

setze_status laeuft "Sicherung anlegen" ""
mkdir -p "$SICHERUNG"
scripts/docker-sicherung.sh "$SICHERUNG" > "$ARBEIT/sicherung.log" 2>&1 ||
    scheitern "Die Sicherung ist fehlgeschlagen, deshalb wurde nicht aktualisiert."

setze_status laeuft "Neue Version laden" ""
if [ -n "${UPDATE_QUELLE:-}" ]; then
    cp "$UPDATE_QUELLE" "$ARBEIT/neu.tar.gz" || scheitern "Die Datei $UPDATE_QUELLE fehlt."
else
    if [ -n "$TOKEN" ]; then
        curl -fsSL -H "Authorization: Bearer $TOKEN" \
            "https://api.github.com/repos/$REPO/tarball/refs/tags/$TAG" -o "$ARBEIT/neu.tar.gz"
    else
        curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/tags/$TAG" -o "$ARBEIT/neu.tar.gz"
    fi || scheitern "Die Version $TAG konnte nicht von GitHub geladen werden."
fi
mkdir "$ARBEIT/neu"
tar -xzf "$ARBEIT/neu.tar.gz" -C "$ARBEIT/neu" --strip-components=1 ||
    scheitern "Die heruntergeladene Datei ist kein gültiges Archiv."
[ -f "$ARBEIT/neu/docker-compose.yml" ] && [ -f "$ARBEIT/neu/app/version.py" ] ||
    scheitern "Das Archiv enthält kein steuy."
NEU="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ARBEIT/neu/app/version.py")"
[ "v$NEU" = "$TAG" ] || scheitern "Das Archiv enthält Version $NEU, erwartet war $TAG."

setze_status laeuft "Programm ersetzen" ""
mkdir -p "$SICHERUNG"
ALT="$SICHERUNG/programm-vor-$TAG.tar.gz"
tar -czf "$ALT" --exclude=./update --exclude=./.env . || scheitern "Der alte Programmstand konnte nicht gesichert werden."
for d in app tests docs scripts migrations .github .githooks .claude; do rm -rf "./$d"; done
cp -a "$ARBEIT/neu/." "$ZIEL/" || scheitern "Kopieren fehlgeschlagen (alter Stand liegt in $ALT)."

setze_status laeuft "Neu bauen und starten" ""
if ! COMPOSE_BAKE=false docker compose up -d --build --wait > "$ARBEIT/bauen.log" 2>&1; then
    setze_status laeuft "Fehler, alter Stand wird wiederhergestellt" ""
    for d in app tests docs scripts migrations .github .githooks .claude; do rm -rf "./$d"; done
    tar -xzf "$ALT" -C "$ZIEL"
    COMPOSE_BAKE=false docker compose up -d --build --wait > /dev/null 2>&1
    scheitern "Das Starten der neuen Version schlug fehl, die alte läuft wieder. Siehe docker compose logs."
fi

setze_status laeuft "Prüfen" ""
ok=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if curl -fsS http://127.0.0.1:8000/gesund > /dev/null 2>&1; then ok=ja; break; fi
    sleep 5
done
[ -n "$ok" ] || scheitern "Die neue Version antwortet nicht. Alter Stand: $ALT, Daten: $SICHERUNG."
setze_status fertig "" "Aktualisiert auf $TAG"
