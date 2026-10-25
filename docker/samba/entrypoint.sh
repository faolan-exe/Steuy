#!/bin/sh
# Steuert Samba über die Datei /freigabe/status, die steuy schreibt (Zeilen "schlüssel=wert"):
#   aktiv=1          Freigabe an (sonst aus)
#   passwort=...     Passwort des Benutzers "scanner" (nur a-z und 0-9)
#   kompatibel=1     auch ältere Scanner zulassen (SMB1)
# Die Datei wird alle 3 Sekunden geprüft. Jede Änderung wird sofort umgesetzt.
# TROCKEN=1: nur einmal lesen und ausgeben, was getan würde (für Tests).
set -u

STATUS="${STATUS_DATEI:-/freigabe/status}"
EINSTELLUNG="${PROTOKOLL_DATEI:-/etc/samba/protokoll.conf}"
BENUTZER=scanner
TROCKEN="${TROCKEN:-0}"
SMBD_PID=""

wert() {
    sed -n "s/^$1=//p" "$STATUS" 2> /dev/null | head -n 1
}

stoppe() {
    if [ -n "$SMBD_PID" ] && kill -0 "$SMBD_PID" 2> /dev/null; then
        kill "$SMBD_PID" 2> /dev/null || true
        wait "$SMBD_PID" 2> /dev/null || true
    fi
    SMBD_PID=""
}

laeuft() {
    [ -n "$SMBD_PID" ] && kill -0 "$SMBD_PID" 2> /dev/null
}

anwenden() {
    aktiv="$(wert aktiv)"
    passwort="$(wert passwort)"
    kompatibel="$(wert kompatibel)"
    case "$passwort" in *[!a-z0-9]*) passwort="" ;; esac

    if [ "$kompatibel" = 1 ]; then
        printf 'server min protocol = NT1\nntlm auth = yes\n' > "$EINSTELLUNG"
        protokoll=NT1
    else
        printf 'server min protocol = SMB2\n' > "$EINSTELLUNG"
        protokoll=SMB2
    fi

    if [ "$aktiv" = 1 ] && [ -n "$passwort" ]; then
        if [ "$TROCKEN" = 1 ]; then
            echo "START protokoll=$protokoll"
            return 0
        fi
        printf '%s\n%s\n' "$passwort" "$passwort" | smbpasswd -s -a "$BENUTZER" > /dev/null 2>&1
        stoppe
        smbd --foreground --no-process-group --debug-stdout &
        SMBD_PID=$!
        echo "Freigabe eingeschaltet (Protokoll ab $protokoll)"
    else
        if [ "$TROCKEN" = 1 ]; then
            echo "STOP"
            return 0
        fi
        stoppe
        echo "Freigabe ausgeschaltet"
    fi
}

trap 'stoppe; exit 0' TERM INT

if [ "$TROCKEN" = 1 ]; then
    anwenden
    exit 0
fi

letzter=""
while true; do
    aktuell="$(md5sum "$STATUS" 2> /dev/null | cut -d ' ' -f 1)"
    # Änderung oder abgestürztes smbd bei eingeschalteter Freigabe: neu anwenden
    if [ "$aktuell" != "$letzter" ] || { [ "$(wert aktiv)" = 1 ] && ! laeuft; }; then
        anwenden
        letzter="$aktuell"
    fi
    sleep 3
done
