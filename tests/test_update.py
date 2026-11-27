import json
import subprocess
import tomllib
import urllib.error
from pathlib import Path

import pytest

from app.domain.update import VersionUngueltig, ist_neuer, lies_version, release_notizen, tag_fuer
from app.services import update as dienst
from app.version import VERSION

ROOT = Path(__file__).parent.parent

RELEASE = {
    "tag_name": "v9.0.0",
    "name": "Version 9",
    "html_url": "https://github.com/x/y/releases/tag/v9.0.0",
    "body": (
        "## Neu\n- **Lieferschein** aus der Rechnung\n- Ziel anpassen\n\n"
        "## Behoben\n* Summe im Editor\n"
    ),
}


@pytest.fixture(autouse=True)
def leere_pruefung():
    dienst._cache.update(zeit=0.0, ergebnis=None)
    yield
    dienst._cache.update(zeit=0.0, ergebnis=None)


@pytest.fixture
def mit_release(monkeypatch, app):
    monkeypatch.setattr(dienst, "_hole_release", lambda: dict(RELEASE))
    with app.app_context():
        yield


def test_version_in_pyproject_und_code_gleich():
    daten = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert daten["project"]["version"] == VERSION


def test_versionen_vergleichen():
    assert lies_version("v1.2.3") == (1, 2, 3) and lies_version("0.10.0") == (0, 10, 0)
    assert ist_neuer("v0.10.0", "0.9.9") and not ist_neuer("v0.2.0", "0.2.0")
    assert tag_fuer("0.3.1") == "v0.3.1"
    for kaputt in ("", "v1", "1.2", "1.2.3-rc1", "latest"):
        with pytest.raises(VersionUngueltig):
            lies_version(kaputt)


def test_release_notizen_gegliedert():
    abschnitte = release_notizen(RELEASE["body"])
    assert abschnitte == [
        ("Neu", ["Lieferschein aus der Rechnung", "Ziel anpassen"]),
        ("Behoben", ["Summe im Editor"]),
    ]
    assert release_notizen("") == []
    assert release_notizen("Nur ein Satz.") == [("Hinweise", ["Nur ein Satz."])]


def test_neue_version_wird_gemeldet(mit_release):
    ergebnis = dienst.pruefe(frisch=True)
    assert (ergebnis.zustand, ergebnis.neueste) == ("neu", "v9.0.0")
    assert ergebnis.notizen[0][0] == "Neu"


def test_aktuelle_version(monkeypatch, app):
    monkeypatch.setattr(dienst, "_hole_release", lambda: {**RELEASE, "tag_name": f"v{VERSION}"})
    with app.app_context():
        assert dienst.pruefe(frisch=True).zustand == "aktuell"


@pytest.mark.parametrize(
    ("fehler", "text"),
    [
        (urllib.error.HTTPError("u", 404, "nf", {}, None), "noch keine veröffentlichte"),
        (urllib.error.HTTPError("u", 500, "x", {}, None), "Fehler 500"),
        (urllib.error.URLError("offline"), "nicht erreichbar"),
        (TimeoutError(), "nicht erreichbar"),
    ],
)
def test_fehler_bei_der_pruefung(monkeypatch, app, fehler, text):
    def kaputt():
        raise fehler

    monkeypatch.setattr(dienst, "_hole_release", kaputt)
    with app.app_context():
        ergebnis = dienst.pruefe(frisch=True)
    assert ergebnis.zustand == "fehler" and text in ergebnis.meldung


def test_seite_zeigt_neue_version_mit_knoepfen(angemeldet, mit_release, app, tmp_path):
    app.config["UPDATE_VERZEICHNIS"] = str(tmp_path)
    seite = angemeldet.get("/einstellungen/update?pruefen=1").get_data(as_text=True)
    assert (
        "Neue Version v9.0.0" in seite and "Das ist neu" in seite and "Das wurde behoben" in seite
    )
    assert "Lieferschein aus der Rechnung" in seite and "Summe im Editor" in seite
    assert ">Updaten<" in seite and ">Überspringen<" in seite
    app.config["UPDATE_VERZEICHNIS"] = ""


def test_seite_zeigt_aktuell(angemeldet, monkeypatch):
    monkeypatch.setattr(dienst, "_hole_release", lambda: {**RELEASE, "tag_name": f"v{VERSION}"})
    seite = angemeldet.get("/einstellungen/update?pruefen=1").get_data(as_text=True)
    assert "Bereits aktuelle Version" in seite and ">Updaten<" not in seite


def test_ueberspringen_und_doch_aktualisieren(angemeldet, mit_release, session, app):
    from app.models import Gewerbe

    angemeldet.get("/einstellungen/update?pruefen=1")
    angemeldet.post("/einstellungen/update/ueberspringen")
    assert session.get(Gewerbe, 1).update_uebersprungen == "v9.0.0"
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert "übersprungen" in seite and "Doch aktualisieren" in seite and ">Updaten<" not in seite
    angemeldet.post("/einstellungen/update/ueberspringen", data={"aktion": "doch"})
    assert session.get(Gewerbe, 1).update_uebersprungen is None


def test_neuere_version_nach_ueberspringen_wird_wieder_angeboten(
    angemeldet, monkeypatch, session, app
):
    from app.models import Gewerbe

    session.get(Gewerbe, 1).update_uebersprungen = "v8.0.0"
    session.commit()
    monkeypatch.setattr(dienst, "_hole_release", lambda: dict(RELEASE))
    seite = angemeldet.get("/einstellungen/update?pruefen=1").get_data(as_text=True)
    assert "Neue Version v9.0.0" in seite and "Doch aktualisieren" not in seite


def test_update_starten_legt_anfrage_ab(angemeldet, mit_release, app, tmp_path):
    app.config["UPDATE_VERZEICHNIS"] = str(tmp_path)
    angemeldet.get("/einstellungen/update?pruefen=1")
    antwort = angemeldet.post("/einstellungen/update/starten")
    assert antwort.status_code == 302
    anfrage = json.loads((tmp_path / "anfrage").read_text())
    assert anfrage["version"] == "v9.0.0"
    assert json.loads((tmp_path / "status.json").read_text())["zustand"] == "angefragt"
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert "Update auf v9.0.0" in seite and "Warte auf den Update-Dienst" in seite
    zweites = angemeldet.post("/einstellungen/update/starten", follow_redirects=True)
    assert "Es läuft bereits ein Update" in zweites.get_data(as_text=True) or "läuft" in (
        zweites.get_data(as_text=True)
    )
    fortschritt = angemeldet.get("/einstellungen/update/status").get_json()
    assert fortschritt["zustand"] == "angefragt" and fortschritt["installiert"] == VERSION
    app.config["UPDATE_VERZEICHNIS"] = ""


def test_ohne_update_ordner_kein_automatisches_update(angemeldet, mit_release, app):
    app.config["UPDATE_VERZEICHNIS"] = ""
    seite = angemeldet.get("/einstellungen/update?pruefen=1").get_data(as_text=True)
    assert "docker compose up -d --build" in seite and ">Updaten<" not in seite
    antwort = angemeldet.post("/einstellungen/update/starten", follow_redirects=True)
    assert "nicht eingerichtet" in antwort.get_data(as_text=True)


def test_fehlgeschlagenes_update_wird_angezeigt(angemeldet, mit_release, app, tmp_path):
    app.config["UPDATE_VERZEICHNIS"] = str(tmp_path)
    (tmp_path / "status.json").write_text(
        json.dumps({"zustand": "fehlgeschlagen", "version": "v9.0.0", "meldung": "Sicherung fehlt"})
    )
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert "fehlgeschlagen" in seite and "Sicherung fehlt" in seite
    app.config["UPDATE_VERZEICHNIS"] = ""


def test_update_nur_mit_einstellungsrecht(client, admin, session):
    from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

    neuer_nutzer(session, "mitarbeiter@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "mitarbeiter@x.example", "passwort": ADMIN_PASSWORT})
    for methode, pfad in (
        ("get", "/einstellungen/update"),
        ("get", "/einstellungen/update/status"),
        ("post", "/einstellungen/update/starten"),
        ("post", "/einstellungen/update/ueberspringen"),
        ("post", "/einstellungen/update/automatik"),
    ):
        assert getattr(client, methode)(pfad).status_code == 403


@pytest.mark.parametrize(
    "skript", ["update-ausfuehren.sh", "lxc-installieren.sh", "update-dienst-einrichten.sh"]
)
def test_skripte_syntaktisch_in_ordnung(skript):
    subprocess.run(["sh", "-n", str(ROOT / "scripts" / skript)], check=True)


def test_update_skript_lehnt_ungueltige_version_ab(tmp_path):
    """Die Anfrage kommt aus dem Container: Nur Versionen der Form vX.Y.Z werden angenommen."""
    (tmp_path / "update").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "version.py").write_text('VERSION = "0.2.0"\n')
    (tmp_path / "update" / "anfrage").write_text('{"version": "v1.0.0; rm -rf /"}')
    subprocess.run(
        ["sh", str(ROOT / "scripts" / "update-ausfuehren.sh")],
        env={"ZIEL": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        check=False,
    )
    status = json.loads((tmp_path / "update" / "status.json").read_text())
    assert status["zustand"] == "fehlgeschlagen" and "Ungültige Version" in status["meldung"]
    assert not (tmp_path / "update" / "anfrage").exists()


# ---------- Automatische Suche ----------


def test_automatik_standardmaessig_an_und_taeglich(mit_release, admin, session):
    from datetime import UTC, datetime, timedelta

    assert admin and dienst.suche_faellig()
    dienst.pruefe(frisch=True)
    gewerbe = dienst.aktuelles_gewerbe()
    assert gewerbe.update_verfuegbar == "v9.0.0" and dienst.hinweis() == "v9.0.0"
    assert not dienst.suche_faellig()
    morgen = datetime.now(UTC) + timedelta(hours=25)
    assert dienst.suche_faellig(morgen)


def test_hinweis_im_dashboard_und_am_symbol(angemeldet, mit_release, session):
    dienst.pruefe(frisch=True)
    seite = angemeldet.get("/").get_data(as_text=True)
    assert "steuy v9.0.0 ist verfügbar" in seite and "mit-punkt" in seite
    assert "nur installiert, wenn du es dort bestätigst" in seite


def test_uebersprungene_version_ohne_hinweis(angemeldet, mit_release, session, admin):
    dienst.pruefe(frisch=True)
    dienst.ueberspringe("v9.0.0", admin.id)
    assert dienst.hinweis() is None
    assert "ist verfügbar" not in angemeldet.get("/").get_data(as_text=True)


def test_automatik_aus_fragt_github_nicht(angemeldet, monkeypatch, app, session):
    aufrufe = []
    monkeypatch.setattr(dienst, "_hole_release", lambda: aufrufe.append(1) or dict(RELEASE))
    antwort = angemeldet.post("/einstellungen/update/automatik", data={})
    assert antwort.status_code == 302
    with app.app_context():
        assert not dienst.suche_faellig()
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert aufrufe == [] and "automatische Suche ist aus" in seite
    # Von Hand suchen geht weiterhin
    seite = angemeldet.get("/einstellungen/update?pruefen=1").get_data(as_text=True)
    assert aufrufe == [1] and "v9.0.0" in seite
    angemeldet.post("/einstellungen/update/automatik", data={"an": "y"})
    with app.app_context():
        assert dienst.aktuelles_gewerbe().update_auto_suchen


def test_hintergrundsuche_installiert_nie(monkeypatch, app, admin, session, tmp_path):
    """Die tägliche Suche merkt sich nur die Version, eine Update-Anfrage entsteht nie."""
    import threading

    app.config["UPDATE_VERZEICHNIS"] = str(tmp_path)
    fertig = threading.Event()
    monkeypatch.setattr(dienst, "pruefe", lambda frisch=False: fertig.set())
    with app.app_context():
        assert dienst.suche_im_hintergrund(app)
    assert fertig.wait(5)
    assert not (tmp_path / "anfrage").exists()
    app.config["UPDATE_VERZEICHNIS"] = ""


# ---------- Fortschritt ----------


@pytest.mark.parametrize(
    ("status", "alter", "erwartet"),
    [
        ({}, 0, "bereit"),
        ({"zustand": "angefragt"}, 10, "wartet"),
        ({"zustand": "angefragt"}, 120, "dienst_fehlt"),
        ({"zustand": "laeuft"}, 60, "laeuft"),
        ({"zustand": "laeuft"}, 30 * 60, "haengt"),
        ({"zustand": "fertig"}, 9999, "fertig"),
        ({"zustand": "fehlgeschlagen"}, 1, "fehlgeschlagen"),
    ],
)
def test_update_lage(status, alter, erwartet):
    from app.domain.update import update_lage

    jetzt = 1_000_000
    assert update_lage({**status, "zeit": jetzt - alter}, jetzt) == erwartet


def _status(tmp_path, **werte):
    (tmp_path / "status.json").write_text(json.dumps({"version": "v9.0.0", **werte}))


def test_seite_zeigt_schritte_und_fortschritt(angemeldet, app, tmp_path, monkeypatch):
    import time

    monkeypatch.setattr(dienst, "_hole_release", lambda: dict(RELEASE))
    app.config["UPDATE_VERZEICHNIS"] = str(tmp_path)
    jetzt = int(time.time())
    _status(
        tmp_path,
        zustand="laeuft",
        nr=3,
        gesamt=6,
        schritt="Version prüfen",
        ausgabe="Entpacken …",
        start=jetzt - 30,
        zeit=jetzt,
    )
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert 'class="erledigt" data-nr="2"' in seite and 'class="aktiv" data-nr="3"' in seite
    assert 'class="offen" data-nr="4"' in seite and "Entpacken …" in seite
    assert "33 %" in seite and "Neu bauen und starten" in seite
    stand = angemeldet.get("/einstellungen/update/status").get_json()
    assert stand["lage"] == "laeuft" and stand["nr"] == 3
    app.config["UPDATE_VERZEICHNIS"] = ""


def test_dienst_reagiert_nicht(angemeldet, app, tmp_path):
    import time

    app.config["UPDATE_VERZEICHNIS"] = str(tmp_path)
    _status(tmp_path, zustand="angefragt", zeit=int(time.time()) - 600)
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert "Update-Dienst auf dem Server reagiert nicht" in seite
    assert "update-dienst-einrichten.sh" in seite
    app.config["UPDATE_VERZEICHNIS"] = ""


def test_fertig_und_fehlgeschlagen(angemeldet, app, tmp_path):
    app.config["UPDATE_VERZEICHNIS"] = str(tmp_path)
    import time

    jetzt = int(time.time())
    _status(
        tmp_path,
        zustand="fertig",
        nr=6,
        gesamt=6,
        start=jetzt - 200,
        zeit=jetzt,
        version=f"v{VERSION}",
    )
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert "abgeschlossen" in seite and "100 %" in seite and "läuft jetzt mit Version" in seite
    # Nach einem Tag ist die Erfolgsmeldung weg
    _status(tmp_path, zustand="fertig", nr=6, gesamt=6, start=1, zeit=100)
    assert "abgeschlossen" not in angemeldet.get("/einstellungen/update").get_data(as_text=True)
    _status(
        tmp_path, zustand="fehlgeschlagen", nr=1, schritt="Sicherung anlegen", meldung="Platte voll"
    )
    seite = angemeldet.get("/einstellungen/update").get_data(as_text=True)
    assert "Fehlgeschlagen bei „Sicherung anlegen“" in seite and "Platte voll" in seite
    assert 'class="fehler" data-nr="1"' in seite
    app.config["UPDATE_VERZEICHNIS"] = ""


def test_schritte_im_skript_wie_in_der_app():
    from app.domain.update import UPDATE_SCHRITTE

    skript = (ROOT / "scripts" / "update-ausfuehren.sh").read_text()
    for nr, name in enumerate(UPDATE_SCHRITTE, 1):
        assert f'schritt {nr} "{name}"' in skript
    assert f"GESAMT={len(UPDATE_SCHRITTE)}" in skript


def _baue_umgebung(tmp_path, bauen_klappt=True):
    """Ein steuy-Ordner mit nachgebauten docker- und curl-Befehlen."""
    import tarfile

    ziel = tmp_path / "steuy"
    (ziel / "app").mkdir(parents=True)
    (ziel / "app" / "version.py").write_text('VERSION = "0.2.0"\n')
    (ziel / "update").mkdir()
    (ziel / "scripts").mkdir()
    for name in ("update-ausfuehren.sh", "docker-sicherung.sh"):
        (ziel / "scripts" / name).write_text((ROOT / "scripts" / name).read_text())
        (ziel / "scripts" / name).chmod(0o755)
    neu = tmp_path / "neu" / "steuy-9.0.0"
    (neu / "app").mkdir(parents=True)
    (neu / "app" / "version.py").write_text('VERSION = "9.0.0"\n')
    (neu / "docker-compose.yml").write_text("services: {}\n")
    archiv = tmp_path / "neu.tar.gz"
    with tarfile.open(archiv, "w:gz") as tar:
        tar.add(neu, arcname="steuy-9.0.0")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(
        "#!/bin/sh\n"
        'case "$*" in *pg_dump*) echo dump;; *tar*) echo ablage;; '
        f'*up*) echo "Image wird gebaut"; exit {0 if bauen_klappt else 1};; esac\n'
    )
    (bin_ / "curl").write_text("#!/bin/sh\nexit 0\n")
    for datei in bin_.iterdir():
        datei.chmod(0o755)
    (ziel / "update" / "anfrage").write_text('{"version": "v9.0.0"}')
    env = {
        "ZIEL": str(ziel),
        "SICHERUNG": str(tmp_path / "sicherung"),
        "UPDATE_QUELLE": str(archiv),
        "PATH": f"{bin_}:/usr/bin:/bin",
    }
    return ziel, env


def test_update_skript_meldet_jeden_schritt_bis_fertig(tmp_path):
    ziel, env = _baue_umgebung(tmp_path)
    lauf = subprocess.run(
        ["sh", str(ziel / "scripts" / "update-ausfuehren.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert lauf.returncode == 0, lauf.stderr
    for nr in range(1, 7):
        assert f"Schritt {nr} von 6" in lauf.stdout
    status = json.loads((ziel / "update" / "status.json").read_text())
    assert status["zustand"] == "fertig" and status["nr"] == 6 and status["von"] == "0.2.0"
    assert status["start"] <= status["zeit"]
    assert 'VERSION = "9.0.0"' in (ziel / "app" / "version.py").read_text()


def test_update_skript_bei_fehler_alter_stand_und_schritt(tmp_path):
    ziel, env = _baue_umgebung(tmp_path, bauen_klappt=False)
    subprocess.run(
        ["sh", str(ziel / "scripts" / "update-ausfuehren.sh")],
        env=env,
        capture_output=True,
        check=False,
        timeout=60,
    )
    status = json.loads((ziel / "update" / "status.json").read_text())
    assert status["zustand"] == "fehlgeschlagen" and status["nr"] == 5
    assert "alte läuft wieder" in status["meldung"]
    assert 'VERSION = "0.2.0"' in (ziel / "app" / "version.py").read_text()
