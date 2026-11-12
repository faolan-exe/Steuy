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
    "ip": '[ "$1 $2 $3" = "link show vmbr0" ] && exit 0; exit 1',
    "pvesh": """
case "$2" in
  /cluster/nextid) echo 105 ;;
  /cluster/resources) echo '[{"vmid":300,"type":"qemu"}]' ;;
esac""",
    "pvesm": """
case "$*" in
  *rootdir*) printf 'Name Type Status\\nlocal-zfs zfspool active\\nlocal-lvm lvmthin active\\n' ;;
  *vztmpl*) printf 'Name Type Status\\nlocal dir active\\n' ;;
  *) printf 'Name Type Status\\nlocal dir active\\n'
     printf 'local-lvm lvmthin active\\nlocal-zfs zfspool active\\n' ;;
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

    def lauf(**umgebung):
        env = {
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
    assert "root-Passwort:" in ergebnis.stdout


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
        ({"STEUY_SPEICHER": "nas"}, "kann keine Container"),
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
