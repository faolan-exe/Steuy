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
    assert "Update auf v9.0.0 läuft" in seite
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
    ):
        assert getattr(client, methode)(pfad).status_code == 403


@pytest.mark.parametrize("skript", ["update-ausfuehren.sh", "lxc-installieren.sh"])
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
