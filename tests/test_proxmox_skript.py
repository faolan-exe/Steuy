"""Das Proxmox-Skript gegen nachgebaute Proxmox-Befehle laufen lassen.

Einen echten Proxmox-Host gibt es in den Tests nicht. Die Platzhalter für pct, pveam, pvesm und
pvesh schreiben jeden Aufruf mit, so prüfen die Tests, was das Skript wirklich tut: welchen
Container es mit welchen Einstellungen anlegt und wann es abbricht.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SKRIPT = Path(__file__).parent.parent / "scripts/proxmox-installieren.sh"

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="bash fehlt")

PLATZHALTER = {
    "id": "echo 0",
    "dpkg": "echo amd64",
    "ip": """
case "$*" in
  "link show vmbr0"|"link show vmbr1") exit 0 ;;
  "-o link show type bridge")
    echo '4: vmbr0: <BROADCAST,MULTICAST,UP> mtu 1500'
    echo '7: vmbr1: <BROADCAST,MULTICAST,UP> mtu 1500' ;;
  *) exit 1 ;;
esac""",
    "pvesh": """
case "$2" in
  /cluster/nextid) echo 105 ;;
  /cluster/resources) echo '[{"vmid":300,"type":"qemu"}]' ;;
esac""",
    "pvesm": """
echo 'Name Type Status Total Used Available %'
case "$*" in
  *rootdir*)
    echo 'local-zfs zfspool active 500000000 1000000 499000000 0.20%'
    echo 'local-lvm lvmthin active 400000000 100000000 300000000 25.00%'
    echo 'nas nfs active 2000000000 500000000 1500000000 25.00%' ;;
  *vztmpl*) echo 'local dir active 90000000 10000000 80000000 11.11%' ;;
  *)
    echo 'local dir active 90000000 10000000 80000000 11.11%'
    echo 'local-lvm lvmthin active 400000000 100000000 300000000 25.00%'
    echo 'local-zfs zfspool active 500000000 1000000 499000000 0.20%'
    echo 'nas nfs active 2000000000 500000000 1500000000 25.00%' ;;
esac""",
    # Dialoge: jede Zeile in $ANTWORTEN beantwortet einen Aufruf. <ja>/<nein> für Ja/Nein-Fragen.
    "whiptail": """
printf "whiptail %s\\n" "$*" >> "$PROTOKOLL"
antwort="$(head -n 1 "$ANTWORTEN")"
tail -n +2 "$ANTWORTEN" > "$ANTWORTEN.neu" && mv "$ANTWORTEN.neu" "$ANTWORTEN"
case "$antwort" in
  "<nein>") exit 1 ;;
  "<ja>") exit 0 ;;
  *) printf '%s' "$antwort" >&2 ;;
esac""",
    "pveam": """
echo "pveam $*" >> "$PROTOKOLL"
case "$1" in
  available)
    echo 'system ubuntu-24.04-standard_24.04-1_amd64.tar.zst'
    echo 'system ubuntu-24.04-standard_24.04-2_amd64.tar.zst'
    echo 'system debian-12-standard_12.7-1_amd64.tar.zst' ;;
  list) echo 'NAME SIZE' ;;
esac""",
    "pct": """
echo "pct $*" >> "$PROTOKOLL"
case "$1" in
  status) for b in $BELEGT; do [ "$b" = "$2" ] && exit 0; done; exit 2 ;;
  exec)
    case "$*" in
      *chpasswd*) cat > /dev/null ;;
      *"addr show"*) echo '2: eth0    inet 192.168.1.77/24 brd 192.168.1.255 scope global eth0' ;;
      *steuy-installieren.sh*) [ -n "$INSTALL_FEHLER" ] && exit 1 ;;
    esac ;;
esac
exit 0""",
}


@pytest.fixture
def proxmox(tmp_path):
    ordner = tmp_path / "bin"
    ordner.mkdir()
    for name, inhalt in PLATZHALTER.items():
        datei = ordner / name
        datei.write_text("#!/bin/sh\n" + inhalt + "\n")
        datei.chmod(0o755)
    protokoll = tmp_path / "aufrufe.log"
    protokoll.touch()

    def lauf(antworten=(), **umgebung):
        datei = tmp_path / "antworten.txt"
        datei.write_text("".join(f"{a}\n" for a in antworten))
        env = {
            "ANTWORTEN": str(datei),
            "PATH": f"{ordner}:{os.environ['PATH']}",
            "PROTOKOLL": str(protokoll),
            "STEUY_JA": "1",
            "BELEGT": "",
            "INSTALL_FEHLER": "",
            **umgebung,
        }
        ergebnis = subprocess.run(
            ["bash", str(SKRIPT)], env=env, capture_output=True, text=True, timeout=60
        )
        return ergebnis, protokoll.read_text()

    return lauf


def _create(aufrufe: str) -> str:
    return next(z for z in aufrufe.splitlines() if z.startswith("pct create"))


def test_standard_legt_container_mit_docker_tauglichen_einstellungen_an(proxmox):
    ergebnis, aufrufe = proxmox()
    assert ergebnis.returncode == 0, ergebnis.stderr
    create = _create(aufrufe)
    assert create.startswith("pct create 105 local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64")
    for teil in (
        "--features nesting=1,keyctl=1",  # ohne Nesting kein Docker im Container
        "--unprivileged 1",
        "--rootfs local-lvm:16",  # LVM-Thin vor ZFS
        "--net0 name=eth0,bridge=vmbr0,ip=dhcp",
        "--cores 2 --memory 2048",
        "--onboot 1",
    ):
        assert teil in create, teil
    assert "pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst" in aufrufe
    reihenfolge = [z.split()[1] for z in aufrufe.splitlines() if z.startswith("pct ")]
    assert reihenfolge.index("create") < reihenfolge.index("start") < reihenfolge.index("exec")
    assert "sh /root/steuy-installieren.sh" in aufrufe
    assert "http://192.168.1.77" in ergebnis.stdout
    assert "root-Passwort" in ergebnis.stdout
    # Standard ohne Rückfragen: Daten im System, nächtliche Sicherung in den Container
    assert "--mp0" not in create and "--mp1" not in create
    assert "--timezone host" in create and "--tags steuy" in create
    assert "steuy-sicherung" in aufrufe and "-mtime +14" in aufrufe
    assert "pct set 105 --description" in aufrufe


def test_feste_adresse_und_eigene_werte(proxmox):
    ergebnis, aufrufe = proxmox(
        STEUY_CTID="210",
        STEUY_HOSTNAME="buchhaltung",
        STEUY_IP="192.168.1.50/24",
        STEUY_GATEWAY="192.168.1.1",
        STEUY_OS="debian-12",
        STEUY_RAM="3072",
        REPO_URL="https://example.org/steuy.git",
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    create = _create(aufrufe)
    assert "pct create 210 local:vztmpl/debian-12-standard_12.7-1_amd64" in create
    assert "--net0 name=eth0,bridge=vmbr0,ip=192.168.1.50/24,gw=192.168.1.1" in create
    assert "--hostname buchhaltung" in create and "--memory 3072" in create
    assert "--ostype debian" in create
    assert "env REPO_URL=https://example.org/steuy.git sh /root/steuy-installieren.sh" in aufrufe


@pytest.mark.parametrize(
    ("umgebung", "meldung"),
    [
        ({"BELEGT": "105"}, "schon vergeben"),
        ({"STEUY_CTID": "300"}, "schon vergeben"),  # Nummer einer VM im Cluster
        ({"STEUY_HOSTNAME": "mein steuy"}, "Hostname"),
        ({"STEUY_RAM": "512"}, "Arbeitsspeicher"),
        ({"STEUY_DISK": "zehn"}, "Zahl"),
        ({"STEUY_IP": "192.168.1.50"}, "Netzmaske"),
        ({"STEUY_IP": "192.168.1.50/24"}, "Gateway"),
        ({"STEUY_BRIDGE": "vmbr9"}, "Bridge"),
        ({"STEUY_SPEICHER": "usb"}, "kann keine Container"),
        ({"STEUY_DATEN": "usb"}, "Datenbank und Belege"),
        ({"STEUY_SICHERUNG": "usb"}, "Sicherungen"),
        ({"STEUY_SICHERUNG": "nas", "STEUY_SICHERUNG_DISK": "2"}, "mindestens 5 GB"),
        ({"STEUY_VORLAGEN_SPEICHER": "local-lvm"}, "keine Vorlagen"),
        ({"STEUY_VLAN": "5000"}, "VLAN"),
        ({"STEUY_OS": "windows"}, "Unbekanntes System"),
    ],
)
def test_falsche_angaben_brechen_vor_dem_anlegen_ab(proxmox, umgebung, meldung):
    ergebnis, aufrufe = proxmox(**umgebung)
    assert ergebnis.returncode != 0
    assert meldung in ergebnis.stderr
    assert "pct create" not in aufrufe


def test_zfs_gibt_einen_hinweis(proxmox):
    ergebnis, _ = proxmox(STEUY_SPEICHER="local-zfs")
    assert ergebnis.returncode == 0
    assert "ZFS" in ergebnis.stdout


def test_fehler_bei_der_installation_laesst_container_zur_fehlersuche_stehen(proxmox):
    ergebnis, aufrufe = proxmox(INSTALL_FEHLER="1")
    assert ergebnis.returncode != 0
    assert "pct enter 105" in ergebnis.stderr and "pct destroy 105" in ergebnis.stderr
    assert "pct destroy" not in aufrufe  # nichts wird ungefragt gelöscht


def test_ohne_proxmox_klare_meldung(tmp_path):
    ordner = tmp_path / "bin"
    ordner.mkdir()
    (ordner / "id").write_text("#!/bin/sh\necho 0\n")
    (ordner / "id").chmod(0o755)
    ergebnis = subprocess.run(
        ["bash", str(SKRIPT)],
        env={"PATH": f"{ordner}:/usr/bin:/bin", "STEUY_JA": "1"},
        capture_output=True,
        text=True,
    )
    assert ergebnis.returncode != 0 and "Proxmox-Host" in ergebnis.stderr


def test_skript_ausfuehrbar_und_in_der_anleitung():
    assert os.access(SKRIPT, os.X_OK)
    anleitung = (SKRIPT.parent.parent / "docs/lxc.md").read_text()
    assert "scripts/proxmox-installieren.sh" in anleitung


def test_eigene_laufwerke_fuer_daten_und_sicherung(proxmox):
    ergebnis, aufrufe = proxmox(
        STEUY_DATEN="local-lvm",
        STEUY_DATEN_DISK="30",
        STEUY_SICHERUNG="nas",
        STEUY_SICHERUNG_DISK="50",
        STEUY_SICHERUNG_TAGE="30",
        STEUY_VLAN="20",
        STEUY_DNS="192.168.1.1",
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    create = _create(aufrufe)
    assert "--rootfs local-lvm:10" in create  # System kleiner, wenn die Daten eigen liegen
    assert "--mp0 local-lvm:30,mp=/var/lib/docker,backup=1" in create
    assert "--mp1 nas:50,mp=/var/backups/steuy,backup=0" in create
    assert "--net0 name=eth0,bridge=vmbr0,ip=dhcp,tag=20" in create
    assert "--nameserver 192.168.1.1" in create
    assert "-mtime +30" in aufrufe


def test_ohne_sicherung_kein_cron(proxmox):
    ergebnis, aufrufe = proxmox(STEUY_SICHERUNG="keine")
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "steuy-sicherung" not in aufrufe and "--mp1" not in _create(aufrufe)


def test_dialog_name_und_laufwerke_werden_abgefragt(proxmox):
    """Einfacher Modus: Name, System-, Daten- und Sicherungslaufwerk wählt man immer selbst."""
    ergebnis, aufrufe = proxmox(
        antworten=[
            "<ja>",  # Willkommen
            "einfach",
            "mein steuy",  # ungültiger Name: Hinweis, dann neu fragen
            "<ja>",  # Hinweis bestätigt
            "buchhaltung",
            "local-lvm",  # System
            "eigenes",  # Datenbank und Belege
            "local-lvm",
            "30",
            "eigenes",  # Sicherungen
            "nas",
            "50",
            "<ja>",  # Zusammenfassung: Anlegen
        ],
        STEUY_JA="",
        STEUY_DIALOG="1",
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    create = _create(aufrufe)
    assert "--hostname buchhaltung" in create
    assert "--mp0 local-lvm:30,mp=/var/lib/docker,backup=1" in create
    assert "--mp1 nas:50,mp=/var/backups/steuy,backup=0" in create
    titel = [z for z in aufrufe.splitlines() if z.startswith("whiptail")]
    for erwartet in (
        "Container-Name",
        "Laufwerk für das System",
        "Datenbank und Belege",
        "Laufwerk für Sicherungen",
        "Zusammenfassung",
    ):
        assert any(erwartet in z for z in titel), erwartet
    # Die Liste zeigt den freien Platz je Laufwerk
    assert any("lvmthin" in z and "GB frei" in z for z in titel)


def test_dialog_erweitert(proxmox):
    ergebnis, aufrufe = proxmox(
        antworten=[
            "<ja>",
            "erweitert",
            "steuy-buero",
            "220",  # CT-ID
            "local-zfs",  # System auf ZFS
            "<ja>",  # ZFS-Hinweis gelesen
            "system",  # Daten im System
            "system",  # Sicherung in den Container
            "4",  # Kerne
            "4096",  # RAM
            "0",  # Swap
            "24",  # System-Laufwerk
            "7",  # Tage
            "vmbr1",  # Bridge aus der Liste
            "",  # kein VLAN
            "192.168.10.5/24",
            "192.168.10.1",
            "",  # DNS wie Host
            "debian-12",
            "<ja>",  # zufälliges Passwort
            "<nein>",  # kein Autostart
            "<ja>",  # Anlegen
        ],
        STEUY_JA="",
        STEUY_DIALOG="1",
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    create = _create(aufrufe)
    assert create.startswith("pct create 220 local:vztmpl/debian-12-standard")
    for teil in (
        "--hostname steuy-buero",
        "--cores 4 --memory 4096 --swap 0",
        "--rootfs local-zfs:24",
        "--net0 name=eth0,bridge=vmbr1,ip=192.168.10.5/24,gw=192.168.10.1",
        "--onboot 0",
        "--ostype debian",
    ):
        assert teil in create, teil
    assert "-mtime +7" in aufrufe


def test_dialog_abbrechen_legt_nichts_an(proxmox):
    ergebnis, aufrufe = proxmox(antworten=["<nein>"], STEUY_JA="", STEUY_DIALOG="1")
    assert ergebnis.returncode == 0
    assert "Abgebrochen" in ergebnis.stdout and "pct create" not in aufrufe
