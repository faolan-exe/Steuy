#!/usr/bin/env bash
# steuy auf Proxmox VE: legt einen fertigen LXC-Container an und installiert steuy darin.
# Auf dem Proxmox-Host (nicht im Container) als root ausführen:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/faolan-exe/Steuy/main/scripts/proxmox-installieren.sh)"
#
# Fragt nach Name und Laufwerken (System, Datenbank und Belege, Sicherungen, Vorlage), auf
# Wunsch nach allem anderen, und richtet dann alles ein: Vorlage laden, Container mit Nesting und
# keyctl anlegen (sonst läuft Docker nicht), steuy installieren, nächtliche Sicherung einrichten.
# Anleitung: docs/lxc.md
#
# Ohne Rückfragen (z. B. für Automatisierung), alle Werte optional:
#   STEUY_JA=1 STEUY_HOSTNAME=steuy STEUY_SPEICHER=local-lvm STEUY_DISK=16 \
#   STEUY_DATEN=system|<speicher> STEUY_DATEN_DISK=20 \
#   STEUY_SICHERUNG=system|keine|<speicher> STEUY_SICHERUNG_DISK=16 STEUY_SICHERUNG_TAGE=14 \
#   STEUY_VORLAGEN_SPEICHER=local STEUY_CTID=210 STEUY_KERNE=2 STEUY_RAM=2048 STEUY_SWAP=512 \
#   STEUY_BRIDGE=vmbr0 STEUY_VLAN= STEUY_IP=dhcp|192.168.1.50/24 STEUY_GATEWAY=192.168.1.1 \
#   STEUY_DNS= STEUY_OS=ubuntu-24.04|debian-12|debian-13 STEUY_AUTOSTART=1 \
#   bash proxmox-installieren.sh
set -euo pipefail

QUELLE="${STEUY_QUELLE:-https://raw.githubusercontent.com/faolan-exe/Steuy/main}"
REPO_URL="${REPO_URL:-}"
TITEL="steuy · Installation auf Proxmox VE"
LOGO_URL="https://raw.githubusercontent.com/faolan-exe/Steuy/main/docs/bilder/steuy-logo.svg"
ANLEITUNG="https://github.com/faolan-exe/Steuy/blob/main/docs/lxc.md"

# ---------------------------------------------------------------------------
# Darstellung: Farben, Zeichen, Logo, Fortschritt
# ---------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    T1=$'\e[38;5;23m'; T2=$'\e[38;5;30m'; T3=$'\e[38;5;31m'; T4=$'\e[38;5;37m'; T5=$'\e[38;5;44m'
    TEAL=$'\e[38;5;37m'; GRUEN=$'\e[38;5;42m'; GELB=$'\e[38;5;178m'; ROT=$'\e[38;5;203m'
    GRAU=$'\e[38;5;245m'; FETT=$'\e[1m'; AUS=$'\e[0m'
    BUNT=1
else
    T1=""; T2=""; T3=""; T4=""; T5=""; TEAL=""; GRUEN=""; GELB=""; ROT=""; GRAU=""; FETT=""; AUS=""
    BUNT=""
fi
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *UTF-8* | *utf8* | *UTF8* | *utf-8*) UTF=1 ;;
    *) UTF="" ;;
esac
if [ -n "$UTF" ]; then
    OK="✔"; NEIN="✖"; INFO="›"; PFEIL="→"
    RAHMEN=("╭" "╮" "╰" "╯" "─" "│")
    SPINNER=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)
else
    OK="ok"; NEIN="!!"; INFO=">"; PFEIL="->"
    RAHMEN=("+" "+" "+" "+" "-" "|")
    SPINNER=("|" "/" "-" "\\")
fi

logo() {
    echo
    if [ -n "$UTF" ]; then
        echo "${T1}   ███████╗████████╗███████╗██╗   ██╗██╗   ██╗${AUS}"
        echo "${T2}   ██╔════╝╚══██╔══╝██╔════╝██║   ██║╚██╗ ██╔╝${AUS}"
        echo "${T3}   ███████╗   ██║   █████╗  ██║   ██║ ╚████╔╝ ${AUS}"
        echo "${T4}   ╚════██║   ██║   ██╔══╝  ██║   ██║  ╚██╔╝  ${AUS}"
        echo "${T5}   ███████║   ██║   ███████╗╚██████╔╝   ██║   ${AUS}"
        echo "${T5}   ╚══════╝   ╚═╝   ╚══════╝ ╚═════╝    ╚═╝   ${AUS}"
    else
        echo "        _"
        echo "    ___| |_ ___ _   _ _   _"
        echo "   / __| __/ _ \\ | | | | | |"
        echo "   \\__ \\ ||  __/ |_| | |_| |"
        echo "   |___/\\__\\___|\\__,_|\\__, |"
        echo "                      |___/"
    fi
    echo "   ${GRAU}Buchhaltung für Kleinunternehmer · Installation auf Proxmox VE${AUS}"
    echo
}

LOG="${STEUY_LOG:-/var/log/steuy-installation.log}"
{ : >> "$LOG"; } 2> /dev/null || LOG="$(mktemp)"

SPINNER_PID=""
SPINNER_TEXT="$(mktemp)"
spinner_aus() {
    if [ -n "$SPINNER_PID" ]; then
        kill "$SPINNER_PID" 2> /dev/null || true
        wait "$SPINNER_PID" 2> /dev/null || true
        SPINNER_PID=""
        printf '\r\e[K'
    fi
}
schritt() { # schritt "Text": zeigt, was gerade passiert (dreht sich, bis ok/fehler)
    echo "$1" > "$SPINNER_TEXT"
    echo "== $1" >> "$LOG"
    if [ -n "$BUNT" ]; then
        if [ -z "$SPINNER_PID" ]; then
            (
                while :; do
                    for zeichen in "${SPINNER[@]}"; do
                        printf '\r\e[K  %s%s%s %s' "$TEAL" "$zeichen" "$AUS" "$(cat "$SPINNER_TEXT" 2> /dev/null)"
                        sleep 0.1
                    done
                done
            ) &
            SPINNER_PID=$!
        fi
    else
        echo "  $PFEIL $1"
    fi
}
ok() {
    spinner_aus
    echo "  ${GRUEN}${OK}${AUS} $1"
}
hinweis() {
    spinner_aus
    echo "  ${GELB}${INFO}${AUS} $1"
}
fehler() {
    spinner_aus
    echo >&2
    echo "  ${ROT}${NEIN} FEHLER:${AUS} $1" >&2
    exit 1
}
abbruch() {
    spinner_aus
    echo
    echo "  ${GRAU}Abgebrochen. Es wurde nichts angelegt.${AUS}"
    exit 0
}
protokoll_zeigen() {
    spinner_aus
    echo "  ${GRAU}Letzte Zeilen aus $LOG:${AUS}" >&2
    tail -n 15 "$LOG" | sed "s/^/    /" >&2
}
ausfuehren() { # ausfuehren "Text" befehl...: mit Fortschritt, Ausgabe ins Protokoll
    local text="$1"
    shift
    schritt "$text"
    if "$@" >> "$LOG" 2>&1; then
        ok "$text"
    else
        protokoll_zeigen
        fehler "$text ist fehlgeschlagen. Ganzes Protokoll: $LOG"
    fi
}

kasten() { # kasten "Titel" "Zeile" ...: Rahmen um Text, Breite nach der längsten Zeile
    local breite=0 zeile i
    for zeile in "$@"; do [ "${#zeile}" -gt "$breite" ] && breite=${#zeile}; done
    breite=$((breite + 4))
    local strich=""
    for ((i = 0; i < breite; i++)); do strich+="${RAHMEN[4]}"; done
    echo "  ${TEAL}${RAHMEN[0]}${strich}${RAHMEN[1]}${AUS}"
    local erste=1
    for zeile in "$@"; do
        local luecke=$((breite - ${#zeile} - 2))
        local fuell=""
        for ((i = 0; i < luecke; i++)); do fuell+=" "; done
        if [ -n "$erste" ]; then
            echo "  ${TEAL}${RAHMEN[5]}${AUS}  ${FETT}${zeile}${AUS}${fuell}${TEAL}${RAHMEN[5]}${AUS}"
            erste=""
        else
            echo "  ${TEAL}${RAHMEN[5]}${AUS}  ${zeile}${fuell}${TEAL}${RAHMEN[5]}${AUS}"
        fi
    done
    echo "  ${TEAL}${RAHMEN[2]}${strich}${RAHMEN[3]}${AUS}"
}

aufraeumen() {
    local rc=$?
    spinner_aus
    rm -f "$SPINNER_TEXT" 2> /dev/null || true
    if [ "$rc" -ne 0 ] && [ -n "${ANGELEGT:-}" ]; then
        echo >&2
        echo "  Der Container $CTID bleibt zur Fehlersuche bestehen: pct enter $CTID" >&2
        echo "  Löschen und neu versuchen: pct stop $CTID; pct destroy $CTID" >&2
    fi
}
trap aufraeumen EXIT
trap 'exit 130' INT TERM

# Whiptail in steuy-Farben
export NEWT_COLORS='
root=white,black
window=white,black
border=cyan,black
shadow=black,black
title=cyan,black
textbox=white,black
button=black,cyan
actbutton=black,cyan
compactbutton=white,black
listbox=white,black
actlistbox=black,cyan
sellistbox=cyan,black
actsellistbox=black,cyan
checkbox=white,black
actcheckbox=black,cyan
entry=white,black
label=white,black
helpline=cyan,black
roottext=cyan,black
'

# ---------------------------------------------------------------------------
# Voraussetzungen
# ---------------------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || fehler "Bitte als root auf dem Proxmox-Host ausführen."
for befehl in pct pveam pvesm pvesh; do
    command -v "$befehl" > /dev/null 2>&1 ||
        fehler "\"$befehl\" fehlt. Das Skript gehört auf den Proxmox-Host, nicht in einen Container.
       Im Container selbst installiert scripts/lxc-installieren.sh."
done
case "$(dpkg --print-architecture 2> /dev/null || uname -m)" in
    amd64 | x86_64) ;;
    *) fehler "steuy gibt es nur für x86_64 (amd64)." ;;
esac

# ---------------------------------------------------------------------------
# Was der Host bietet
# ---------------------------------------------------------------------------
naechste_id() { pvesh get /cluster/nextid 2> /dev/null || echo 100; }

# "name typ frei_gb" je aktivem Speicher mit dem gewünschten Inhalt (rootdir oder vztmpl)
speicher_liste() {
    pvesm status -content "$1" 2> /dev/null |
        awk 'NR > 1 && $3 == "active" {printf "%s %s %.0f\n", $1, $2, $6 / 1048576}'
}
speicher_typ() { pvesm status 2> /dev/null | awk -v s="$1" '$1 == s {print $2}'; }

# Lieber LVM-Thin als ZFS (Docker im Container, siehe docs/lxc.md), sonst der erste
speicher_vorschlag() {
    local liste
    liste="$(speicher_liste rootdir)"
    echo "$liste" | awk '$2 == "lvmthin" {print $1; exit}' | grep . ||
        echo "$liste" | awk '$2 != "zfspool" {print $1; exit}' | grep . ||
        echo "$liste" | awk '{print $1; exit}'
}

bridges() {
    ip -o link show type bridge 2> /dev/null | awk -F': ' '{print $2}' | cut -d@ -f1 | grep -v '^$' || true
}

CTID="${STEUY_CTID:-$(naechste_id)}"
NAME="${STEUY_HOSTNAME:-steuy}"
KERNE="${STEUY_KERNE:-2}"
RAM="${STEUY_RAM:-2048}"
SWAP="${STEUY_SWAP:-512}"
SPEICHER="${STEUY_SPEICHER:-$(speicher_vorschlag)}"
DISK="${STEUY_DISK:-}"
DATEN="${STEUY_DATEN:-system}"
DATEN_DISK="${STEUY_DATEN_DISK:-20}"
SICHERUNG="${STEUY_SICHERUNG:-system}"
SICHERUNG_DISK="${STEUY_SICHERUNG_DISK:-16}"
SICHERUNG_TAGE="${STEUY_SICHERUNG_TAGE:-14}"
VORLAGEN="${STEUY_VORLAGEN_SPEICHER:-$(speicher_liste vztmpl | awk '{print $1; exit}')}"
BRIDGE="${STEUY_BRIDGE:-$(bridges | head -n 1)}"
BRIDGE="${BRIDGE:-vmbr0}"
VLAN="${STEUY_VLAN:-}"
IP="${STEUY_IP:-dhcp}"
GATEWAY="${STEUY_GATEWAY:-}"
DNS="${STEUY_DNS:-}"
OS="${STEUY_OS:-ubuntu-24.04}"
AUTOSTART="${STEUY_AUTOSTART:-1}"
PASSWORT="${STEUY_PASSWORT:-}"

[ -n "$SPEICHER" ] || fehler "Kein Speicher für Container gefunden (pvesm status -content rootdir)."
[ -n "$VORLAGEN" ] || fehler "Kein Speicher für Vorlagen gefunden (pvesm status -content vztmpl)."

# ---------------------------------------------------------------------------
# Rückfragen
# ---------------------------------------------------------------------------
wt() { whiptail --backtitle "$TITEL" "$@" 3>&1 1>&2 2>&3; }

eingabe() { # eingabe "Titel" "Frage" "Vorgabe"
    wt --title "$1" --inputbox "\n$2" 12 72 "$3" || abbruch
}

speicher_wahl() { # speicher_wahl "Titel" "Text" inhalt vorgabe
    local titel="$1" text="$2" inhalt="$3" vorgabe="$4"
    local eintraege=() name typ frei
    while read -r name typ frei; do
        [ -n "$name" ] || continue
        eintraege+=("$name" "$(printf '%-10s %6s GB frei' "$typ" "$frei")" "$([ "$name" = "$vorgabe" ] && echo ON || echo OFF)")
    done < <(speicher_liste "$inhalt")
    wt --title "$titel" --radiolist "\n$text\n\nLeertaste wählt, Enter bestätigt." 20 76 8 "${eintraege[@]}" || abbruch
}

ganzzahl_ok() { [[ "$1" =~ ^[0-9]+$ ]]; }
name_ok() { [[ "$1" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; }

DIALOG=""
if [ -z "${STEUY_JA:-}" ] && { [ -t 0 ] || [ -n "${STEUY_DIALOG:-}" ]; } && command -v whiptail > /dev/null 2>&1; then
    DIALOG=1
fi

if [ -n "$DIALOG" ]; then
    clear 2> /dev/null || true
    logo
    wt --title "Willkommen" --yesno "\nDieses Skript legt einen neuen LXC-Container an und installiert steuy darin: Docker, Webserver, Datenbank, zufällige Zugangsdaten und auf Wunsch eine nächtliche Sicherung.\n\nDu wählst den Namen und die Laufwerke selbst, alles andere ist sinnvoll vorbelegt und unter \"Erweitert\" einstellbar.\n\nAm Ende steht die Adresse im Browser bereit. Dauer: etwa 5 bis 15 Minuten.\n\nLos geht's?" 20 76 || abbruch

    MODUS="$(wt --title "Einstellungen" --menu "\nWie ausführlich?" 14 76 2 \
        "einfach" "Name und Laufwerke wählen, Rest empfohlen (2 Kerne, 2 GB)" \
        "erweitert" "Alles selbst festlegen: Größe, Netzwerk, System, Passwort")" || abbruch

    # Name: immer selbst
    while :; do
        NAME="$(eingabe "Container-Name" "Name des Containers (Hostname im Netzwerk). Buchstaben, Ziffern und Bindestriche, z. B. steuy oder buchhaltung." "$NAME")"
        name_ok "$NAME" && break
        wt --title "Container-Name" --msgbox "\n\"$NAME\" geht nicht: nur Buchstaben, Ziffern und Bindestriche, nicht am Anfang oder Ende." 10 72 || true
    done

    if [ "$MODUS" = "erweitert" ]; then
        while :; do
            CTID="$(eingabe "Container-Nummer" "Nummer des Containers (CT-ID), ab 100. Vorschlag: die nächste freie." "$CTID")"
            ganzzahl_ok "$CTID" && [ "$CTID" -ge 100 ] && break
        done
    fi

    # Laufwerke: immer selbst
    SPEICHER="$(speicher_wahl "Laufwerk für das System" "Wohin kommt der Container selbst (Betriebssystem, Docker, steuy)?" rootdir "$SPEICHER")"
    if [ "$(speicher_typ "$SPEICHER")" = "zfspool" ]; then
        wt --title "Hinweis zu ZFS" --msgbox "\n$SPEICHER ist ZFS. Docker läuft darin ab Proxmox VE 8.1 (ZFS 2.2). Mit älteren Versionen besser LVM-Thin oder einen Verzeichnis-Speicher wählen." 11 72 || true
    fi

    DATEN_WAHL="$(wt --title "Datenbank und Belege" --menu "\nWo sollen Datenbank und Belege liegen? Ein eigenes Laufwerk lässt sich später einfacher vergrößern, umziehen oder auf schnellen Speicher legen." 17 76 2 \
        "system" "Mit auf dem System-Laufwerk (einfach)" \
        "eigenes" "Eigenes Laufwerk für Datenbank und Belege")" || abbruch
    if [ "$DATEN_WAHL" = "eigenes" ]; then
        DATEN="$(speicher_wahl "Laufwerk für Datenbank und Belege" "Wo sollen Datenbank und Belege liegen? Das Laufwerk ist in der Proxmox-Sicherung enthalten." rootdir "$SPEICHER")"
        while :; do
            DATEN_DISK="$(eingabe "Größe für Datenbank und Belege" "Größe in GB (mindestens 5). Belege wachsen mit den Jahren, 20 GB reichen für viele." "$DATEN_DISK")"
            ganzzahl_ok "$DATEN_DISK" && [ "$DATEN_DISK" -ge 5 ] && break
        done
    else
        DATEN="system"
    fi

    SICHERUNG_WAHL="$(wt --title "Nächtliche Sicherung" --menu "\nsteuy sichert jede Nacht um 2 Uhr Datenbank und Belege. Wohin?\n\nAm sichersten auf ein anderes Laufwerk als das System, z. B. einen NAS-Speicher in Proxmox." 19 76 3 \
        "eigenes" "Eigenes Laufwerk für Sicherungen (empfohlen)" \
        "system" "In den Container, Ordner /var/backups/steuy" \
        "keine" "Keine automatische Sicherung")" || abbruch
    case "$SICHERUNG_WAHL" in
        eigenes)
            andere="$(speicher_liste rootdir | awk -v s="$SPEICHER" '$1 != s {print $1; exit}')"
            SICHERUNG="$(speicher_wahl "Laufwerk für Sicherungen" "Wohin sollen die nächtlichen Sicherungen? Am besten ein anderes Laufwerk als für das System." rootdir "${andere:-$SPEICHER}")"
            while :; do
                SICHERUNG_DISK="$(eingabe "Größe für Sicherungen" "Größe in GB (mindestens 5)." "$SICHERUNG_DISK")"
                ganzzahl_ok "$SICHERUNG_DISK" && [ "$SICHERUNG_DISK" -ge 5 ] && break
            done
            ;;
        *) SICHERUNG="$SICHERUNG_WAHL" ;;
    esac

    if [ "$(speicher_liste vztmpl | wc -l)" -gt 1 ]; then
        VORLAGEN="$(speicher_wahl "Speicher für die Vorlage" "Wohin wird die System-Vorlage (ca. 130 MB) heruntergeladen?" vztmpl "$VORLAGEN")"
    fi

    if [ "$MODUS" = "erweitert" ]; then
        while :; do
            KERNE="$(eingabe "CPU-Kerne" "Anzahl CPU-Kerne (mindestens 1, empfohlen 2)." "$KERNE")"
            ganzzahl_ok "$KERNE" && [ "$KERNE" -ge 1 ] && break
        done
        while :; do
            RAM="$(eingabe "Arbeitsspeicher" "Arbeitsspeicher in MB (mindestens 1536, empfohlen 2048)." "$RAM")"
            ganzzahl_ok "$RAM" && [ "$RAM" -ge 1536 ] && break
        done
        while :; do
            SWAP="$(eingabe "Swap" "Swap in MB (0 für keinen)." "$SWAP")"
            ganzzahl_ok "$SWAP" && break
        done
        while :; do
            DISK="$(eingabe "Größe System-Laufwerk" "Größe in GB (mindestens 8)." "${DISK:-$([ "$DATEN" = system ] && echo 16 || echo 10)}")"
            ganzzahl_ok "$DISK" && [ "$DISK" -ge 8 ] && break
        done
        if [ "$SICHERUNG" != "keine" ]; then
            while :; do
                SICHERUNG_TAGE="$(eingabe "Sicherungen aufheben" "Wie viele Tage sollen Sicherungen aufgehoben werden? Ältere werden gelöscht." "$SICHERUNG_TAGE")"
                ganzzahl_ok "$SICHERUNG_TAGE" && [ "$SICHERUNG_TAGE" -ge 1 ] && break
            done
        fi
        BRUECKEN=()
        while read -r b; do [ -z "$b" ] || BRUECKEN+=("$b"); done < <(bridges)
        if [ "${#BRUECKEN[@]}" -gt 1 ]; then
            eintraege=()
            for b in "${BRUECKEN[@]}"; do eintraege+=("$b" "Netzwerk-Bridge" "$([ "$b" = "$BRIDGE" ] && echo ON || echo OFF)"); done
            BRIDGE="$(wt --title "Netzwerk" --radiolist "\nÜber welche Bridge kommt der Container ins Netz?" 16 72 6 "${eintraege[@]}")" || abbruch
        else
            BRIDGE="$(eingabe "Netzwerk" "Netzwerk-Bridge" "$BRIDGE")"
        fi
        VLAN="$(eingabe "VLAN" "VLAN-Tag, leer lassen ohne VLAN." "$VLAN")"
        while :; do
            IP="$(eingabe "Adresse" "dhcp oder feste Adresse mit Netzmaske, z. B. 192.168.1.50/24. Tipp: Mit DHCP im Router eine feste Adresse für den Container reservieren." "$IP")"
            [ "$IP" = "dhcp" ] && break
            [[ "$IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ ]] || continue
            GATEWAY="$(eingabe "Gateway" "Gateway, meist der Router, z. B. 192.168.1.1." "$GATEWAY")"
            [[ "$GATEWAY" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] && break
        done
        DNS="$(eingabe "DNS-Server" "DNS-Server, leer lassen für die Einstellung des Hosts." "$DNS")"
        OS="$(wt --title "Betriebssystem" --radiolist "\nWelches System soll im Container laufen?" 14 72 3 \
            "ubuntu-24.04" "Ubuntu 24.04 LTS (getestet, empfohlen)" "$([ "$OS" = ubuntu-24.04 ] && echo ON || echo OFF)" \
            "debian-12" "Debian 12" "$([ "$OS" = debian-12 ] && echo ON || echo OFF)" \
            "debian-13" "Debian 13" "$([ "$OS" = debian-13 ] && echo ON || echo OFF)")" || abbruch
        if wt --title "root-Passwort" --yes-button "Zufällig" --no-button "Selbst festlegen" --yesno "\nFür die Konsole in der Proxmox-Oberfläche braucht der Container ein root-Passwort.\n\nZufällig: ein starkes Passwort erzeugen, es wird am Ende angezeigt." 13 72; then
            PASSWORT=""
        else
            while :; do
                PASSWORT="$(wt --title "root-Passwort" --passwordbox "\nroot-Passwort (mindestens 8 Zeichen)" 10 72)" || abbruch
                WIEDERHOLT="$(wt --title "root-Passwort" --passwordbox "\nNoch einmal zur Bestätigung" 10 72)" || abbruch
                [ "${#PASSWORT}" -ge 8 ] && [ "$PASSWORT" = "$WIEDERHOLT" ] && break
                wt --title "root-Passwort" --msgbox "\nDie Passwörter stimmen nicht überein oder sind kürzer als 8 Zeichen." 9 72 || true
            done
            EIGENES_PASSWORT=1
        fi
        if wt --title "Autostart" --yesno "\nSoll der Container mit dem Proxmox-Host starten?" 9 72; then
            AUTOSTART=1
        else
            AUTOSTART=0
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Prüfen
# ---------------------------------------------------------------------------
ganzzahl() { ganzzahl_ok "$2" || fehler "$1 muss eine Zahl sein, war: \"$2\"."; }
[ -n "$DISK" ] || DISK=$([ "$DATEN" = system ] && echo 16 || echo 10)
ganzzahl "Die CT-ID" "$CTID"
ganzzahl "Die Anzahl Kerne" "$KERNE"
ganzzahl "Der Arbeitsspeicher" "$RAM"
ganzzahl "Der Swap" "$SWAP"
ganzzahl "Die Festplattengröße" "$DISK"
ganzzahl "Die Größe für Datenbank und Belege" "$DATEN_DISK"
ganzzahl "Die Größe für Sicherungen" "$SICHERUNG_DISK"
ganzzahl "Die Aufbewahrung der Sicherungen" "$SICHERUNG_TAGE"
[ "$CTID" -ge 100 ] || fehler "Die CT-ID muss 100 oder größer sein."
[ "$KERNE" -ge 1 ] || fehler "Mindestens 1 Kern."
[ "$RAM" -ge 1536 ] || fehler "Mindestens 1536 MB Arbeitsspeicher (empfohlen 2048)."
[ "$DISK" -ge 8 ] || fehler "Mindestens 8 GB Festplatte."
name_ok "$NAME" || fehler "Der Hostname darf nur Buchstaben, Ziffern und Bindestriche enthalten."
if pct status "$CTID" > /dev/null 2>&1 ||
    pvesh get /cluster/resources --type vm --output-format json 2> /dev/null | grep -Eq "\"vmid\": ?${CTID}[,}]"; then
    fehler "Die Nummer $CTID ist schon vergeben. Wähle eine andere (STEUY_CTID=...)."
fi
container_speicher() { speicher_liste rootdir | awk '{print $1}' | grep -qx "$1"; }
container_speicher "$SPEICHER" || fehler "Speicher \"$SPEICHER\" kann keine Container aufnehmen."
if [ "$DATEN" != "system" ]; then
    container_speicher "$DATEN" ||
        fehler "Speicher \"$DATEN\" (Datenbank und Belege) kann keine Container-Laufwerke aufnehmen."
    [ "$DATEN_DISK" -ge 5 ] || fehler "Für Datenbank und Belege mindestens 5 GB."
fi
case "$SICHERUNG" in
    keine | system) ;;
    *)
        container_speicher "$SICHERUNG" ||
            fehler "Speicher \"$SICHERUNG\" (Sicherungen) kann keine Container-Laufwerke aufnehmen."
        [ "$SICHERUNG_DISK" -ge 5 ] || fehler "Für Sicherungen mindestens 5 GB."
        ;;
esac
speicher_liste vztmpl | awk '{print $1}' | grep -qx "$VORLAGEN" ||
    fehler "Speicher \"$VORLAGEN\" kann keine Vorlagen aufnehmen."
ip link show "$BRIDGE" > /dev/null 2>&1 || fehler "Netzwerk-Bridge \"$BRIDGE\" gibt es nicht."
if [ -n "$VLAN" ]; then
    { ganzzahl_ok "$VLAN" && [ "$VLAN" -ge 1 ] && [ "$VLAN" -le 4094 ]; } ||
        fehler "Der VLAN-Tag muss zwischen 1 und 4094 liegen."
fi
if [ "$IP" = "dhcp" ]; then
    NETZ="name=eth0,bridge=$BRIDGE,ip=dhcp"
else
    [[ "$IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ ]] ||
        fehler "Feste Adresse bitte mit Netzmaske angeben, z. B. 192.168.1.50/24."
    [[ "$GATEWAY" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] ||
        fehler "Für eine feste Adresse fehlt das Gateway (STEUY_GATEWAY=...)."
    NETZ="name=eth0,bridge=$BRIDGE,ip=$IP,gw=$GATEWAY"
fi
[ -z "$VLAN" ] || NETZ="$NETZ,tag=$VLAN"
case "$OS" in
    ubuntu-24.04) MUSTER='^ubuntu-24\.04-standard_'; OSTYP=ubuntu; OSNAME="Ubuntu 24.04" ;;
    debian-12) MUSTER='^debian-12-standard_'; OSTYP=debian; OSNAME="Debian 12" ;;
    debian-13) MUSTER='^debian-13-standard_'; OSTYP=debian; OSNAME="Debian 13" ;;
    *) fehler "Unbekanntes System \"$OS\" (ubuntu-24.04, debian-12 oder debian-13)." ;;
esac

beschreibung_daten() {
    if [ "$DATEN" = "system" ]; then echo "auf dem System-Laufwerk"; else echo "$DATEN, $DATEN_DISK GB (eigenes Laufwerk)"; fi
}
beschreibung_sicherung() {
    case "$SICHERUNG" in
        keine) echo "keine automatische Sicherung" ;;
        system) echo "jede Nacht in den Container, $SICHERUNG_TAGE Tage" ;;
        *) echo "jede Nacht auf $SICHERUNG ($SICHERUNG_DISK GB), $SICHERUNG_TAGE Tage" ;;
    esac
}
ZUSAMMENFASSUNG=(
    "Das wird eingerichtet"
    ""
    "Container     $CTID · $NAME · $OSNAME"
    "Leistung      $KERNE Kerne · $RAM MB RAM · $SWAP MB Swap"
    "System        $SPEICHER, $DISK GB"
    "Daten         $(beschreibung_daten)"
    "Sicherungen   $(beschreibung_sicherung)"
    "Vorlage       $VORLAGEN"
    "Netzwerk      $BRIDGE${VLAN:+ · VLAN $VLAN} · ${IP}${GATEWAY:+ über $GATEWAY}${DNS:+ · DNS $DNS}"
    "Autostart     $([ "$AUTOSTART" = 1 ] && echo ja || echo nein)"
)

if [ -n "$DIALOG" ]; then
    text=""
    for zeile in "${ZUSAMMENFASSUNG[@]:2}"; do text+="$zeile\n"; done
    wt --title "Zusammenfassung" --yes-button "Anlegen" --no-button "Abbrechen" \
        --yesno "\n${text}\nJetzt anlegen und steuy installieren?" 20 78 || abbruch
    clear 2> /dev/null || true
fi

logo
kasten "${ZUSAMMENFASSUNG[@]}"
echo
if [ "$(speicher_typ "$SPEICHER")" = "zfspool" ]; then
    hinweis "$SPEICHER ist ZFS: Docker läuft darauf ab Proxmox VE 8.1 (ZFS 2.2)."
    hinweis "Mit älteren Versionen besser local-lvm oder einen Verzeichnis-Speicher nehmen."
fi
echo "  ${GRAU}Protokoll: $LOG${AUS}"
echo

# ---------------------------------------------------------------------------
# Vorlage
# ---------------------------------------------------------------------------
schritt "Vorlagenliste aktualisieren"
pveam update >> "$LOG" 2>&1 || true
VORLAGE="$(pveam available --section system 2> /dev/null | awk '{print $2}' | grep -E "$MUSTER" | sort -V | tail -n 1 || true)"
if [ -z "$VORLAGE" ]; then
    # Offline: eine schon heruntergeladene Vorlage nehmen
    VORLAGE="$(pveam list "$VORLAGEN" 2> /dev/null | awk '{print $1}' | sed 's|.*/||' | grep -E "$MUSTER" | sort -V | tail -n 1 || true)"
fi
[ -n "$VORLAGE" ] || fehler "Keine Vorlage für $OSNAME gefunden. Prüfen mit: pveam available --section system"
if pveam list "$VORLAGEN" 2> /dev/null | grep -q "$VORLAGE"; then
    ok "Vorlage $VORLAGE ist schon da"
else
    ausfuehren "Vorlage $VORLAGE nach $VORLAGEN laden" pveam download "$VORLAGEN" "$VORLAGE"
fi

# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------
# shellcheck disable=SC2054 # Die Kommas gehören zu den pct-Optionen, sie trennen keine Elemente
ERSTELLEN=(
    pct create "$CTID" "$VORLAGEN:vztmpl/$VORLAGE"
    --hostname "$NAME"
    --cores "$KERNE" --memory "$RAM" --swap "$SWAP"
    --rootfs "$SPEICHER:$DISK"
    --net0 "$NETZ"
    --unprivileged 1 --features nesting=1,keyctl=1
    --onboot "$AUTOSTART" --ostype "$OSTYP" --tags steuy --timezone host
    --description "steuy wird eingerichtet ..."
)
# Datenbank und Belege liegen in Docker: eigenes Laufwerk für /var/lib/docker, in der
# Proxmox-Sicherung enthalten (backup=1)
[ "$DATEN" = "system" ] || ERSTELLEN+=(--mp0 "$DATEN:$DATEN_DISK,mp=/var/lib/docker,backup=1")
# Sicherungen auf eigenem Laufwerk, nicht in der Proxmox-Sicherung (die Daten sind schon drin)
case "$SICHERUNG" in
    keine | system) ;;
    *) ERSTELLEN+=(--mp1 "$SICHERUNG:$SICHERUNG_DISK,mp=/var/backups/steuy,backup=0") ;;
esac
[ -z "$DNS" ] || ERSTELLEN+=(--nameserver "$DNS")

ausfuehren "Container $CTID \"$NAME\" anlegen" "${ERSTELLEN[@]}"
ANGELEGT=1
ausfuehren "Container starten" pct start "$CTID"

schritt "Auf das Netzwerk warten"
online=""
for _ in $(seq 1 60); do
    if pct exec "$CTID" -- sh -c 'ip -4 route | grep -q "^default" && getent hosts github.com' > /dev/null 2>&1; then
        online=ja
        break
    fi
    sleep 2
done
[ -n "$online" ] || fehler "Der Container kommt nicht ins Internet (DHCP, Gateway, DNS prüfen)."
ok "Netzwerk und Internet sind da"

# root-Passwort für die Konsole in der Proxmox-Oberfläche
if [ -z "$PASSWORT" ]; then
    PASSWORT="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 20 || true)"
fi
printf 'root:%s\n' "$PASSWORT" | pct exec "$CTID" -- chpasswd || fehler "Das root-Passwort ließ sich nicht setzen."
ok "root-Passwort gesetzt"

ausfuehren "Grundpakete im Container" pct exec "$CTID" -- sh -c "export DEBIAN_FRONTEND=noninteractive
    apt-get update -q && apt-get install -y -q curl ca-certificates cron"
ausfuehren "Installationsskript laden" \
    pct exec "$CTID" -- curl -fsSL "$QUELLE/scripts/lxc-installieren.sh" -o /root/steuy-installieren.sh

# steuy installieren: Die Schritte des Skripts im Container („==> 1/5 …“) erscheinen einzeln
INSTALLATION=(pct exec "$CTID" -- sh /root/steuy-installieren.sh)
[ -z "$REPO_URL" ] || INSTALLATION=(pct exec "$CTID" -- env REPO_URL="$REPO_URL" sh /root/steuy-installieren.sh)
schritt "steuy installieren"
set +e
"${INSTALLATION[@]}" 2>&1 | {
    aktuell="steuy installieren"
    while IFS= read -r zeile; do
        printf '%s\n' "$zeile" >> "$LOG"
        case "$zeile" in
            "==> "*)
                [ "$aktuell" = "steuy installieren" ] || ok "$aktuell"
                aktuell="Installation · ${zeile#==> [0-9]/[0-9] }"
                schritt "$aktuell"
                ;;
        esac
    done
    spinner_aus
}
rc=${PIPESTATUS[0]}
set -e
SPINNER_PID=""
if [ "$rc" -ne 0 ]; then
    protokoll_zeigen
    fehler "Die Installation im Container ist fehlgeschlagen. Ganzes Protokoll: $LOG"
fi
letzter="$(cat "$SPINNER_TEXT" 2> /dev/null)"
[ "$letzter" = "steuy installieren" ] || ok "$letzter"
ok "steuy ist installiert und antwortet"

if [ "$SICHERUNG" != "keine" ]; then
    ausfuehren "Nächtliche Sicherung einrichten (2 Uhr, $SICHERUNG_TAGE Tage)" pct exec "$CTID" -- sh -c "
        mkdir -p /var/backups/steuy && chmod 700 /var/backups/steuy
        cat > /etc/cron.d/steuy-sicherung << 'CRON'
# steuy: Datenbank und Belege jede Nacht sichern, ältere Sicherungen löschen
0 2 * * * root cd /opt/steuy && scripts/docker-sicherung.sh /var/backups/steuy >> /var/log/steuy-sicherung.log 2>&1 && find /var/backups/steuy -mindepth 1 -maxdepth 1 -type d -name 'steuy-*' -mtime +$SICHERUNG_TAGE -exec rm -rf {} +
CRON
        chmod 644 /etc/cron.d/steuy-sicherung
        systemctl enable --now cron > /dev/null 2>&1 || true"
fi

ADRESSE="$(pct exec "$CTID" -- ip -4 -o addr show dev eth0 2> /dev/null | awk '{print $4}' | cut -d/ -f1 | head -n 1)"
NOTIZ="<div align='center'><a href='https://github.com/faolan-exe/Steuy'><img src='$LOGO_URL' alt='steuy' width='180'/></a>

**Buchhaltung für Kleinunternehmer**

[http://${ADRESSE:-?}](http://${ADRESSE:-?}) · [Anleitung]($ANLEITUNG)

Daten: $(beschreibung_daten) · Sicherungen: $(beschreibung_sicherung)
</div>"
pct set "$CTID" --description "$NOTIZ" >> "$LOG" 2>&1 || true
ok "Notizen in Proxmox gesetzt"
ANGELEGT=""

ZEILEN=(
    "steuy läuft in Container $CTID"
    ""
    "Im Browser      http://${ADRESSE:-<IP-des-Containers>}"
    "Konsole         pct enter $CTID"
)
if [ -n "${EIGENES_PASSWORT:-}" ]; then
    ZEILEN+=("root-Passwort   wie von dir festgelegt")
else
    ZEILEN+=("root-Passwort   $PASSWORT" "                bitte im Passwortmanager sichern")
fi
ZEILEN+=(
    "Sicherungen     $(beschreibung_sicherung)"
    ""
    "Im Browser startet der Einrichtungsassistent."
    "Im eigenen Netz geht http://, aus dem Internet"
    "antwortet steuy nur über https://."
    "Updates: in steuy unter Einstellungen → Update."
)
echo
kasten "${ZEILEN[@]}"
echo
echo "  ${GRAU}Anleitung, Zugriff von unterwegs, Sicherung zurückspielen: $ANLEITUNG${AUS}"
echo
