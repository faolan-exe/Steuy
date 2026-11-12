"""Von außen nur über HTTPS, im eigenen Netz auch ohne (app/web/nur_https.py)."""

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT

AUSSEN = {"REMOTE_ADDR": "203.0.113.7"}
HEIMNETZ = {"REMOTE_ADDR": "192.168.178.20"}


def test_heimnetz_ohne_https_geht(client, admin):
    antwort = client.get("/anmelden", environ_base=HEIMNETZ)
    assert antwort.status_code == 200 and "Anmelden" in antwort.get_data(as_text=True)


@pytest.mark.parametrize(
    "pfad", ["/", "/anmelden", "/rechnungen", "/k/irgendwas", "/static/css/app.css"]
)
def test_von_aussen_ohne_https_gesperrt(client, admin, pfad):
    antwort = client.get(pfad, environ_base=AUSSEN)
    assert antwort.status_code == 403
    assert "nur verschlüsselt erreichbar" in antwort.get_data(as_text=True)


def test_sperrseite_verraet_nichts_auch_angemeldet(angemeldet, admin):
    antwort = angemeldet.get("/", environ_base=AUSSEN)
    seite = antwort.get_data(as_text=True)
    assert antwort.status_code == 403
    assert admin.name not in seite and admin.email not in seite and "Dashboard" not in seite
    assert antwort.headers["Cache-Control"] == "no-store"


def test_anmeldung_von_aussen_ohne_https_wird_nicht_verarbeitet(client, admin):
    antwort = client.post(
        "/anmelden",
        data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT},
        environ_base=AUSSEN,
    )
    assert antwort.status_code == 403
    # Keine Sitzung entstanden: im Heimnetz ist man weiter abgemeldet
    assert client.get("/", environ_base=HEIMNETZ).status_code == 302


def test_von_aussen_mit_https_geht(client, admin):
    antwort = client.get("/anmelden", base_url="https://steuy.example.de", environ_base=AUSSEN)
    assert antwort.status_code == 200
    assert antwort.headers["Strict-Transport-Security"].startswith("max-age=")


def test_mit_oeffentlicher_https_adresse_wird_umgeleitet(app, client, admin, monkeypatch):
    monkeypatch.setitem(app.config, "BASIS_URL", "https://rechnung.example.de")
    antwort = client.get("/rechnungen?filter=offen", environ_base=AUSSEN)
    assert antwort.status_code == 308
    assert antwort.headers["Location"] == "https://rechnung.example.de/rechnungen?filter=offen"
    # Abgeschickte Formulare werden nie umgeleitet, sondern abgelehnt
    assert client.post("/anmelden", data={}, environ_base=AUSSEN).status_code == 403


def test_eigene_netze_und_abschalten(app, client, admin, monkeypatch):
    monkeypatch.setitem(app.config, "INTERNE_NETZE", "203.0.113.0/24")
    assert client.get("/anmelden", environ_base=AUSSEN).status_code == 200
    monkeypatch.setitem(app.config, "INTERNE_NETZE", "")
    monkeypatch.setitem(app.config, "NUR_HTTPS_VON_AUSSEN", False)
    assert client.get("/anmelden", environ_base=AUSSEN).status_code == 200


@pytest.mark.parametrize(
    ("weitergeleitet_fuer", "protokoll", "erwartet"),
    [
        ("203.0.113.9", "https", 200),  # Proxy mit Zertifikat davor: Besucher von außen, https
        ("203.0.113.9", "http", 403),  # Router leitet Port 80 durch: von außen ohne https
        ("192.168.178.20", "http", 200),  # im Heimnetz über nginx
        # Gefälscht: Der Besucher behauptet eine Heimnetz-Adresse, nginx hängt die echte an
        ("192.168.178.20, 203.0.113.9", "http", 403),
    ],
)
def test_hinter_reverse_proxy(
    app, client, admin, monkeypatch, weitergeleitet_fuer, protokoll, erwartet
):
    """Wie im Container: nginx (PROXY_ANZAHL=1) gibt Adresse und Protokoll weiter."""
    monkeypatch.setattr(app, "wsgi_app", ProxyFix(app.wsgi_app, x_for=1, x_proto=1))
    antwort = client.get(
        "/anmelden",
        headers={"X-Forwarded-For": weitergeleitet_fuer, "X-Forwarded-Proto": protokoll},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert antwort.status_code == erwartet


def test_lxc_nginx_reicht_adresse_und_protokoll_weiter():
    """Ohne diese Kopfzeilen sähe steuy hinter nginx jeden Besucher als 127.0.0.1 (intern)."""
    from pathlib import Path

    skript = (Path(__file__).parent.parent / "scripts/lxc-installieren.sh").read_text()
    assert "PROXY_ANZAHL=1" in skript
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in skript
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in skript
