"""Statische Prüfungen der Docker-Dateien. Gebaut und gestartet wird das Image in der CI."""

import os
from pathlib import Path

WURZEL = Path(__file__).parent.parent


def test_startskripte_ausfuehrbar():
    for name in (
        "docker-start.sh",
        "docker-sicherung.sh",
        "docker-wiederherstellen.sh",
        "lxc-installieren.sh",
    ):
        assert os.access(WURZEL / "scripts" / name, os.X_OK), name


def test_keine_festen_zugangsdaten():
    compose = (WURZEL / "docker-compose.yml").read_text()
    assert "${SECRET_KEY:?" in compose and "${POSTGRES_PASSWORD:?" in compose
    # App nur lokal erreichbar, nach außen über Reverse Proxy
    assert '"127.0.0.1:${PORT:-8000}:8000"' in compose


def test_image_laeuft_ohne_root_und_migriert():
    dockerfile = (WURZEL / "Dockerfile").read_text()
    assert "USER steuy" in dockerfile
    start = (WURZEL / "scripts/docker-start.sh").read_text()
    assert start.index("flask db upgrade") < start.index("gunicorn")


def test_lxc_anleitung_und_skript_passen_zusammen():
    anleitung = (WURZEL / "docs/lxc.md").read_text()
    skript = (WURZEL / "scripts/lxc-installieren.sh").read_text()
    # Die Anleitung verweist auf das Skript und nennt die nötigen Container-Features
    assert "scripts/lxc-installieren.sh" in anleitung
    assert "nesting=1" in anleitung and "keyctl" in anleitung
    # Das Skript legt die .env nur an, wenn sie fehlt, und überschreibt nie Daten
    assert "if [ ! -f .env ]" in skript
    assert "down -v" not in skript
    # Vorhandener Code (z. B. per Archiv kopiert) wird übernommen statt neu geklont
    assert 'elif [ -f "$ZIEL/docker-compose.yml" ]' in skript
    # Das Archiv aus der Anleitung darf keine Zugangsdaten vom Entwicklungsrechner mitnehmen
    assert "--exclude=.env" in anleitung
    # Der Startseite (README) ist die Anleitung verlinkt
    assert "docs/lxc.md" in (WURZEL / "README.md").read_text()


def test_lxc_skript_richtet_webserver_passend_zur_app_ein():
    skript = (WURZEL / "scripts/lxc-installieren.sh").read_text()
    config = (WURZEL / "app/config.py").read_text()
    # nginx darf Uploads nicht kleiner begrenzen als die App (100 MB), sonst scheitern Belege
    assert "MAX_CONTENT_LENGTH = 100 * 1024 * 1024" in config
    assert "client_max_body_size 100m;" in skript
    # Hinter dem Webserver braucht die App die Adresse der Besucher für die Anmeldesperre
    assert "PROXY_ANZAHL=1" in skript and "proxy_set_header X-Forwarded-For" in skript
    assert "proxy_pass http://127.0.0.1:8000;" in skript
    # Die App lauscht nur lokal, nginx ist der einzige Zugang von außen
    assert '"127.0.0.1:${PORT:-8000}:8000"' in (WURZEL / "docker-compose.yml").read_text()


def test_lxc_skript_ueberschreibt_keine_einstellungen():
    skript = (WURZEL / "scripts/lxc-installieren.sh").read_text()
    # nginx-Datei nur anlegen, wenn sie fehlt (sonst ginge HTTPS von certbot beim Update verloren)
    assert 'if [ ! -f "$SEITE" ]' in skript
    assert "if [ ! -f .env ]" in skript
    # Das fertige Skript prüft selbst, ob alles antwortet, und nennt die Adresse
    assert "http://127.0.0.1/gesund" in skript and "hostname -I" in skript


def test_lxc_skript_kommt_mit_vorhandenem_docker_ohne_compose_zurecht():
    """Gefunden im echten Test: Docker aus den Ubuntu-Paketen hat kein „docker compose“."""
    skript = (WURZEL / "scripts/lxc-installieren.sh").read_text()
    pruefung = skript.index("docker compose version")
    start = skript.index("COMPOSE_BAKE=false docker compose up")
    assert pruefung < start, "Das Compose-Plugin muss vor dem Start geprüft werden"
    assert "docker-compose-v2" in skript and "docker-compose-plugin" in skript


def test_lxc_skript_nennt_die_echte_adresse_nicht_ein_docker_netz():
    """Gefunden im Container-Test: „hostname -I“ nennt die Docker-Netze oft zuerst."""
    skript = (WURZEL / "scripts/lxc-installieren.sh").read_text()
    assert "ip -4 route get" in skript
    # „hostname -I | awk '{print $1}'“ nur noch als Rückfall, nie als erste Wahl
    zuerst = skript.index('ADRESSE="$(ip -4 route get')
    rueckfall = skript.index('ADRESSE="$(hostname -I')
    assert zuerst < rueckfall
