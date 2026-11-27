#!/bin/sh
# Führt ein Update aus, das die App in den Ordner update/ angefragt hat.
# Läuft als root über den systemd-Dienst steuy-update (eingerichtet von update-dienst-einrichten.sh).
# Ablauf: sichern, neue Version laden und prüfen, Code ersetzen, neu bauen, prüfen.
# Klappt etwas nicht, wird der alte Code wiederhergestellt: die Daten bleiben unberührt.
# Den Fortschritt (Schritt x von 6, letzte Ausgabe) schreibt es laufend nach update/status.json,
# die Seite Einstellungen → Update zeigt ihn an. Die Schritte stehen auch in app/domain/update.py.
#
# Zum Testen: UPDATE_QUELLE=/pfad/zu/version.tar.gz nimmt eine lokale Datei statt GitHub.
set -u

ZIEL="${ZIEL:-/opt/steuy}"
UPDATE="$ZIEL/update"
STATUS="$UPDATE/status.json"
SICHERUNG="${SICHERUNG:-/var/backups/steuy}"
ARBEIT="$(mktemp -d /tmp/steuy-update.XXXXXX)"
GESAMT=6
export COMPOSE_BAKE=false
START="$(date +%s)"
trap 'rm -rf "$ARBEIT"' EXIT

cd "$ZIEL" || exit 1

# Text für JSON: ohne Steuerzeichen, Anführungszeichen und Backslashes geschützt, gekürzt
json_text() { printf '%s' "$1" | tr -d '\000-\037' | sed 's/\\/\\\\/g; s/"/\\"/g' | cut -c1-200; }

setze_status() { # Zustand, Schritt-Nr, Schritt, Meldung, letzte Ausgabe
    # Erst im eigenen (root-)Arbeitsordner schreiben, dann verschieben: Der Ordner update/ ist
    # für die App beschreibbar. Ein dort untergeschobener Symlink darf root nicht dazu bringen,
    # eine fremde Datei zu überschreiben (mv ersetzt den Link selbst, statt ihm zu folgen).
    printf '{"zustand":"%s","version":"%s","von":"%s","nr":%s,"gesamt":%s,"schritt":"%s","meldung":"%s","ausgabe":"%s","start":%s,"zeit":%s}\n' \
        "$1" "$(json_text "${TAG:-}")" "$(json_text "${VON:-}")" "${2:-0}" "$GESAMT" \
        "$(json_text "$3")" "$(json_text "$4")" "$(json_text "${5:-}")" "$START" "$(date +%s)" \
        > "$ARBEIT/status.json"
    chmod 644 "$ARBEIT/status.json"
    chown 1000:1000 "$ARBEIT/status.json" 2> /dev/null || true
    mv -f "$ARBEIT/status.json" "$STATUS"
}

NR=0
SCHRITT=""
schritt() { # Nr, Name
    NR="$1"
    SCHRITT="$2"
    echo "==> Schritt $NR von $GESAMT: $SCHRITT"
    setze_status laeuft "$NR" "$SCHRITT" "" ""
}

# Befehl im Hintergrund ausführen und alle 2 Sekunden die letzte Ausgabezeile melden,
# damit man sieht, dass etwas passiert (Bauen dauert mehrere Minuten)
mit_fortschritt() { # Logdatei, Befehl...
    log="$1"
    shift
    : > "$log"
    "$@" > "$log" 2>&1 &
    pid=$!
    while kill -0 "$pid" 2> /dev/null; do
        setze_status laeuft "$NR" "$SCHRITT" "" "$(tail -n 1 "$log" 2> /dev/null)"
        sleep 2
    done
    wait "$pid"
}

scheitern() { # Meldung
    echo "FEHLER: $1" >&2
    setze_status fehlgeschlagen "$NR" "$SCHRITT" "$1" ""
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

schritt 1 "Sicherung anlegen"
mkdir -p "$SICHERUNG"
mit_fortschritt "$ARBEIT/sicherung.log" scripts/docker-sicherung.sh "$SICHERUNG" ||
    scheitern "Die Sicherung ist fehlgeschlagen, deshalb wurde nicht aktualisiert."

schritt 2 "Neue Version laden"
if [ -n "${UPDATE_QUELLE:-}" ]; then
    cp "$UPDATE_QUELLE" "$ARBEIT/neu.tar.gz" || scheitern "Die Datei $UPDATE_QUELLE fehlt."
elif [ -n "$TOKEN" ]; then
    mit_fortschritt "$ARBEIT/laden.log" curl -fsSL -H "Authorization: Bearer $TOKEN" \
        "https://api.github.com/repos/$REPO/tarball/refs/tags/$TAG" -o "$ARBEIT/neu.tar.gz" ||
        scheitern "Die Version $TAG konnte nicht von GitHub geladen werden."
else
    mit_fortschritt "$ARBEIT/laden.log" curl -fsSL \
        "https://codeload.github.com/$REPO/tar.gz/refs/tags/$TAG" -o "$ARBEIT/neu.tar.gz" ||
        scheitern "Die Version $TAG konnte nicht von GitHub geladen werden."
fi

schritt 3 "Version prüfen"
mkdir "$ARBEIT/neu"
tar -xzf "$ARBEIT/neu.tar.gz" -C "$ARBEIT/neu" --strip-components=1 ||
    scheitern "Die heruntergeladene Datei ist kein gültiges Archiv."
[ -f "$ARBEIT/neu/docker-compose.yml" ] && [ -f "$ARBEIT/neu/app/version.py" ] ||
    scheitern "Das Archiv enthält kein steuy."
NEU="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ARBEIT/neu/app/version.py")"
[ "v$NEU" = "$TAG" ] || scheitern "Das Archiv enthält Version $NEU, erwartet war $TAG."

schritt 4 "Programm ersetzen"
ALT="$SICHERUNG/programm-vor-$TAG.tar.gz"
tar -czf "$ALT" --exclude=./update --exclude=./.env . || scheitern "Der alte Programmstand konnte nicht gesichert werden."
for d in app tests docs scripts migrations .github .githooks .claude; do rm -rf "./$d"; done
cp -a "$ARBEIT/neu/." "$ZIEL/" || scheitern "Kopieren fehlgeschlagen (alter Stand liegt in $ALT)."

schritt 5 "Neu bauen und starten"
if ! mit_fortschritt "$ARBEIT/bauen.log" docker compose up -d --build --wait; then
    SCHRITT="Fehler, alter Stand wird wiederhergestellt"
    setze_status laeuft "$NR" "$SCHRITT" "" "$(tail -n 1 "$ARBEIT/bauen.log")"
    for d in app tests docs scripts migrations .github .githooks .claude; do rm -rf "./$d"; done
    tar -xzf "$ALT" -C "$ZIEL"
    docker compose up -d --build --wait > /dev/null 2>&1
    scheitern "Das Starten der neuen Version schlug fehl, die alte läuft wieder. Siehe docker compose logs."
fi

schritt 6 "Neue Version prüfen"
ok=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if curl -fsS http://127.0.0.1:8000/gesund > /dev/null 2>&1; then ok=ja; break; fi
    sleep 5
done
[ -n "$ok" ] || scheitern "Die neue Version antwortet nicht. Alter Stand: $ALT, Daten: $SICHERUNG."
NR=$GESAMT
setze_status fertig "$GESAMT" "Fertig" "Aktualisiert auf $TAG" ""
echo "==> Fertig: $TAG"
