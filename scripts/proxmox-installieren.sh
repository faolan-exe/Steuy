#!/usr/bin/env bash
# steuy auf Proxmox VE: legt einen fertigen LXC-Container an und installiert steuy darin.
# Auf dem Proxmox-Host (nicht im Container) als root ausführen:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/faolan-exe/Steuy/main/scripts/proxmox-installieren.sh)"
#
# Fragt nach Standard- oder eigenen Einstellungen und richtet dann alles ein: Vorlage laden,
# Container mit Nesting und keyctl anlegen (sonst läuft Docker nicht), starten, steuy mit
# scripts/lxc-installieren.sh installieren und die Adresse anzeigen. Anleitung: docs/lxc.md
#
# Ohne Rückfragen (z. B. für Automatisierung), alle Werte optional:
#   STEUY_JA=1 STEUY_CTID=210 STEUY_HOSTNAME=steuy STEUY_KERNE=2 STEUY_RAM=2048 \
#   STEUY_DISK=16 STEUY_SPEICHER=local-lvm STEUY_BRIDGE=vmbr0 STEUY_IP=dhcp \
#   STEUY_OS=ubuntu-24.04 bash proxmox-installieren.sh
# Feste Adresse: STEUY_IP=192.168.1.50/24 STEUY_GATEWAY=192.168.1.1
set -euo pipefail

QUELLE="${STEUY_QUELLE:-https://raw.githubusercontent.com/faolan-exe/Steuy/main}"
REPO_URL="${REPO_URL:-}"
TITEL="steuy für Proxmox VE"

# ---------- Ausgabe ----------
if [ -t 1 ]; then
    GRUEN=$'\e[32m'; GELB=$'\e[33m'; ROT=$'\e[31m'; FETT=$'\e[1m'; AUS=$'\e[0m'
else
    GRUEN=""; GELB=""; ROT=""; FETT=""; AUS=""
fi
schritt() { echo "${GRUEN}==>${AUS} ${FETT}$1${AUS}"; }
hinweis() { echo "${GELB}    $1${AUS}"; }
fehler() {
    echo >&2
    echo "${ROT}FEHLER:${AUS} $1" >&2
    exit 1
}

# ---------- Voraussetzungen ----------
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

# ---------- Vorschläge ----------
naechste_id() { pvesh get /cluster/nextid 2> /dev/null || echo 100; }

# Erster Speicher, der Container-Festplatten aufnehmen kann (lieber LVM-Thin als ZFS, siehe docs/lxc.md)
speicher_vorschlag() {
    local liste
    liste="$(pvesm status -content rootdir 2> /dev/null | awk 'NR > 1 && $3 == "active" {print $1 " " $2}')"
    echo "$liste" | awk '$2 == "lvmthin" {print $1; exit}' | grep . ||
        echo "$liste" | awk '$2 != "zfspool" {print $1; exit}' | grep . ||
        echo "$liste" | awk '{print $1; exit}'
}

vorlagen_speicher() {
    pvesm status -content vztmpl 2> /dev/null | awk 'NR > 1 && $3 == "active" {print $1; exit}'
}

CTID="${STEUY_CTID:-$(naechste_id)}"
NAME="${STEUY_HOSTNAME:-steuy}"
KERNE="${STEUY_KERNE:-2}"
RAM="${STEUY_RAM:-2048}"
DISK="${STEUY_DISK:-16}"
SPEICHER="${STEUY_SPEICHER:-$(speicher_vorschlag)}"
BRIDGE="${STEUY_BRIDGE:-vmbr0}"
IP="${STEUY_IP:-dhcp}"
GATEWAY="${STEUY_GATEWAY:-}"
OS="${STEUY_OS:-ubuntu-24.04}"
VORLAGEN="${STEUY_VORLAGEN_SPEICHER:-$(vorlagen_speicher)}"

[ -n "$SPEICHER" ] || fehler "Kein Speicher für Container gefunden (pvesm status -content rootdir)."
[ -n "$VORLAGEN" ] || fehler "Kein Speicher für Vorlagen gefunden (pvesm status -content vztmpl)."

# ---------- Rückfragen ----------
frage() { # frage "Text" "Vorgabe" -> Antwort auf stdout
    whiptail --title "$TITEL" --inputbox "$1" 10 64 "$2" 3>&1 1>&2 2>&3
}

if [ -z "${STEUY_JA:-}" ] && [ -t 0 ] && command -v whiptail > /dev/null 2>&1; then
    whiptail --title "$TITEL" --yesno "Dieses Skript legt einen neuen LXC-Container an und installiert steuy darin:
Docker, Webserver, Datenbank und zufällige Zugangsdaten.

Vorschlag:
  Container $CTID \"$NAME\", $KERNE Kerne, $RAM MB RAM, $DISK GB auf $SPEICHER
  Netzwerk $BRIDGE, Adresse per DHCP, System $OS

Weiter?" 17 72 || exit 0

    if whiptail --title "$TITEL" --menu "Einstellungen" 12 64 2 \
        "standard" "Vorschlag übernehmen (empfohlen)" \
        "eigene" "Selbst festlegen" 3>&1 1>&2 2>&3 | grep -q eigene; then
        CTID="$(frage "Nummer des Containers (CT-ID)" "$CTID")"
        NAME="$(frage "Hostname" "$NAME")"
        KERNE="$(frage "CPU-Kerne (mindestens 1, empfohlen 2)" "$KERNE")"
        RAM="$(frage "Arbeitsspeicher in MB (mindestens 1536, empfohlen 2048)" "$RAM")"
        DISK="$(frage "Festplatte in GB (mindestens 8, empfohlen 16 oder mehr)" "$DISK")"
        SPEICHER="$(frage "Speicher für die Festplatte ($(pvesm status -content rootdir | awk 'NR > 1 {printf "%s ", $1}'))" "$SPEICHER")"
        BRIDGE="$(frage "Netzwerk-Bridge" "$BRIDGE")"
        IP="$(frage "Adresse: dhcp oder fest mit Netzmaske, z. B. 192.168.1.50/24" "$IP")"
        if [ "$IP" != "dhcp" ]; then
            GATEWAY="$(frage "Gateway (meist der Router), z. B. 192.168.1.1" "$GATEWAY")"
        fi
        OS="$(whiptail --title "$TITEL" --menu "Betriebssystem im Container" 12 64 3 \
            "ubuntu-24.04" "Ubuntu 24.04 LTS (getestet, empfohlen)" \
            "debian-12" "Debian 12" \
            "debian-13" "Debian 13" 3>&1 1>&2 2>&3)"
    fi
fi

# ---------- Prüfen ----------
ganzzahl() { [[ "$2" =~ ^[0-9]+$ ]] || fehler "$1 muss eine Zahl sein, war: \"$2\"."; }
ganzzahl "Die CT-ID" "$CTID"
ganzzahl "Die Anzahl Kerne" "$KERNE"
ganzzahl "Der Arbeitsspeicher" "$RAM"
ganzzahl "Die Festplattengröße" "$DISK"
[ "$CTID" -ge 100 ] || fehler "Die CT-ID muss 100 oder größer sein."
[ "$KERNE" -ge 1 ] || fehler "Mindestens 1 Kern."
[ "$RAM" -ge 1536 ] || fehler "Mindestens 1536 MB Arbeitsspeicher (empfohlen 2048)."
[ "$DISK" -ge 8 ] || fehler "Mindestens 8 GB Festplatte."
[[ "$NAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] ||
    fehler "Der Hostname darf nur Buchstaben, Ziffern und Bindestriche enthalten."
if pct status "$CTID" > /dev/null 2>&1 ||
    pvesh get /cluster/resources --type vm --output-format json 2> /dev/null | grep -Eq "\"vmid\": ?${CTID}[,}]"; then
    fehler "Die Nummer $CTID ist schon vergeben. Wähle eine andere (STEUY_CTID=...)."
fi
pvesm status -content rootdir 2> /dev/null | awk 'NR > 1 {print $1}' | grep -qx "$SPEICHER" ||
    fehler "Speicher \"$SPEICHER\" kann keine Container aufnehmen."
ip link show "$BRIDGE" > /dev/null 2>&1 || fehler "Netzwerk-Bridge \"$BRIDGE\" gibt es nicht."
if [ "$IP" = "dhcp" ]; then
    NETZ="name=eth0,bridge=$BRIDGE,ip=dhcp"
else
    [[ "$IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ ]] ||
        fehler "Feste Adresse bitte mit Netzmaske angeben, z. B. 192.168.1.50/24."
    [[ "$GATEWAY" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] ||
        fehler "Für eine feste Adresse fehlt das Gateway (STEUY_GATEWAY=...)."
    NETZ="name=eth0,bridge=$BRIDGE,ip=$IP,gw=$GATEWAY"
fi
case "$OS" in
    ubuntu-24.04) MUSTER='^ubuntu-24\.04-standard_'; OSTYP=ubuntu ;;
    debian-12) MUSTER='^debian-12-standard_'; OSTYP=debian ;;
    debian-13) MUSTER='^debian-13-standard_'; OSTYP=debian ;;
    *) fehler "Unbekanntes System \"$OS\" (ubuntu-24.04, debian-12 oder debian-13)." ;;
esac
if [ "$(pvesm status 2> /dev/null | awk -v s="$SPEICHER" '$1 == s {print $2}')" = "zfspool" ]; then
    hinweis "Hinweis: $SPEICHER ist ZFS. Docker läuft darauf ab Proxmox VE 8.1 (ZFS 2.2)."
    hinweis "Mit älteren Versionen besser local-lvm oder einen Verzeichnis-Speicher nehmen."
fi

# ---------- Vorlage ----------
schritt "1/5 Vorlage für $OS"
pveam update > /dev/null 2>&1 || hinweis "Vorlagenliste konnte nicht aktualisiert werden, nehme die vorhandene."
VORLAGE="$(pveam available --section system 2> /dev/null | awk '{print $2}' | grep -E "$MUSTER" | sort -V | tail -n 1 || true)"
if [ -z "$VORLAGE" ]; then
    # Offline: eine schon heruntergeladene Vorlage nehmen
    VORLAGE="$(pveam list "$VORLAGEN" 2> /dev/null | awk '{print $1}' | sed 's|.*/||' | grep -E "$MUSTER" | sort -V | tail -n 1 || true)"
fi
[ -n "$VORLAGE" ] || fehler "Keine Vorlage für $OS gefunden. Prüfen mit: pveam available --section system"
if pveam list "$VORLAGEN" 2> /dev/null | grep -q "$VORLAGE"; then
    echo "    $VORLAGE ist schon vorhanden."
else
    echo "    Lade $VORLAGE nach $VORLAGEN ..."
    pveam download "$VORLAGEN" "$VORLAGE" > /dev/null || fehler "Die Vorlage konnte nicht geladen werden."
fi

# ---------- Container ----------
schritt "2/5 Container $CTID \"$NAME\" anlegen"
pct create "$CTID" "$VORLAGEN:vztmpl/$VORLAGE" \
    --hostname "$NAME" \
    --cores "$KERNE" --memory "$RAM" --swap 512 \
    --rootfs "$SPEICHER:$DISK" \
    --net0 "$NETZ" \
    --unprivileged 1 --features nesting=1,keyctl=1 \
    --onboot 1 --ostype "$OSTYP" --tags steuy \
    --description "steuy: Buchhaltung für Kleinunternehmer. Anleitung: https://github.com/faolan-exe/Steuy/blob/main/docs/lxc.md" \
    > /dev/null || fehler "Der Container konnte nicht angelegt werden (siehe Meldung oben)."
ANGELEGT=1
# shellcheck disable=SC2154 # rc wird in der Falle selbst gesetzt
trap 'rc=$?; if [ "$rc" -ne 0 ] && [ -n "${ANGELEGT:-}" ]; then
    echo >&2
    echo "Der Container $CTID bleibt zur Fehlersuche bestehen: pct enter $CTID" >&2
    echo "Löschen und neu versuchen: pct stop $CTID; pct destroy $CTID" >&2
fi' EXIT

schritt "3/5 Container starten und auf das Netzwerk warten"
pct start "$CTID"
online=""
for _ in $(seq 1 60); do
    if pct exec "$CTID" -- sh -c 'ip -4 route | grep -q "^default" && getent hosts github.com' > /dev/null 2>&1; then
        online=ja
        break
    fi
    sleep 2
done
[ -n "$online" ] || fehler "Der Container kommt nicht ins Internet (DHCP, Gateway, DNS prüfen)."

# Zufälliges root-Passwort für die Konsole in der Proxmox-Oberfläche
PASSWORT="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 20 || true)"
printf 'root:%s\n' "$PASSWORT" | pct exec "$CTID" -- chpasswd

schritt "4/5 steuy installieren (Docker, Webserver, steuy; dauert einige Minuten)"
pct exec "$CTID" -- sh -c "export DEBIAN_FRONTEND=noninteractive
    apt-get update -q > /dev/null && apt-get install -y -q curl ca-certificates > /dev/null" ||
    fehler "Grundpakete im Container konnten nicht installiert werden."
pct exec "$CTID" -- curl -fsSL "$QUELLE/scripts/lxc-installieren.sh" -o /root/steuy-installieren.sh ||
    fehler "Das Installationsskript konnte nicht geladen werden ($QUELLE)."
if [ -n "$REPO_URL" ]; then
    pct exec "$CTID" -- env REPO_URL="$REPO_URL" sh /root/steuy-installieren.sh
else
    pct exec "$CTID" -- sh /root/steuy-installieren.sh
fi

schritt "5/5 Fertig"
ADRESSE="$(pct exec "$CTID" -- ip -4 -o addr show dev eth0 2> /dev/null | awk '{print $4}' | cut -d/ -f1 | head -n 1)"
pct set "$CTID" --description "steuy: http://${ADRESSE:-?}

Anleitung, Updates, Sicherung: https://github.com/faolan-exe/Steuy/blob/main/docs/lxc.md" > /dev/null || true
ANGELEGT=""

echo
echo "=============================================================="
echo " ${FETT}steuy läuft in Container $CTID.${AUS}"
echo
echo "   Öffne im Browser:   ${FETT}http://${ADRESSE:-<IP-des-Containers>}${AUS}"
echo
echo "   Konsole:            pct enter $CTID"
echo "   root-Passwort:      $PASSWORT"
echo "                       (für die Konsole in der Proxmox-Oberfläche,"
echo "                        bitte im Passwortmanager sichern)"
echo
echo " Im Browser startet der Einrichtungsassistent. Die Verbindung"
echo " ist nicht verschlüsselt, nutze sie nur im eigenen Netz."
echo " Updates: in steuy unter Einstellungen → Update."
echo " Sicherung und Zugriff von unterwegs: docs/lxc.md"
echo "=============================================================="
