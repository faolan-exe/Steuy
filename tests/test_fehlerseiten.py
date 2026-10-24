# ruff: noqa: F811  (Fixtures werden importiert und als Parameter genutzt)
import io

from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401


def text(antwort) -> str:
    return antwort.get_data(as_text=True)


def test_404_ist_deutsch_mit_weg_zurueck(angemeldet):
    antwort = angemeldet.get("/gibt-es-nicht")
    seite = text(antwort)
    assert antwort.status_code == 404
    assert "Seite nicht gefunden" in seite and "Zur Übersicht" in seite
    assert "Not Found" not in seite and "history.back()" in seite


def test_405_nach_neuladen_ist_verstaendlich(angemeldet):
    antwort = angemeldet.get("/rechnungen/neu")
    assert antwort.status_code == 405
    assert "wenn man eine Seite neu lädt" in text(antwort)


def test_403_nennt_den_weg_zu_den_rechten(client, admin, session):
    neuer_nutzer(session, "ma@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "ma@x.example", "passwort": ADMIN_PASSWORT})
    antwort = client.get("/auswertung")
    assert antwort.status_code == 403
    assert "Dafür fehlt dir die Berechtigung" in text(antwort) and "Forbidden" not in text(antwort)


def test_zu_grosse_datei(angemeldet, app):
    app.config["MAX_CONTENT_LENGTH"] = 1000
    try:
        antwort = angemeldet.post(
            "/belege/hochladen",
            data={"dateien": (io.BytesIO(b"x" * 5000), "gross.pdf")},
            content_type="multipart/form-data",
        )
    finally:
        app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
    assert antwort.status_code == 413 and "Die Datei ist zu groß" in text(antwort)


def test_abgelaufenes_formular_erklaert_sich(app, client, admin):
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        antwort = client.post("/anmelden", data={"email": "a@b.de", "passwort": "x"})
    finally:
        app.config["WTF_CSRF_ENABLED"] = False
    assert antwort.status_code == 400
    assert "Die Seite war zu lange geöffnet" in text(antwort)
    assert "CSRF" not in text(antwort)


def test_interner_fehler_ohne_datenbank_und_ohne_details(app, angemeldet, monkeypatch):
    def kaputt():
        raise RuntimeError("geheimer Pfad /opt/steuy/.env")

    monkeypatch.setitem(app.view_functions, "allgemein.suche_seite", kaputt)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        antwort = angemeldet.get("/suche?q=test")
    finally:
        app.config["PROPAGATE_EXCEPTIONS"] = True
    assert antwort.status_code == 500
    seite = text(antwort)
    assert "Da ist etwas schiefgelaufen" in seite and "geheimer Pfad" not in seite
    assert "Traceback" not in seite


def test_gesund_bleibt_json(client, admin):
    assert client.get("/gesund").get_json()["status"] == "ok"


def test_neuladen_nach_zahlungsfehler_fuehrt_zur_rechnung(angemeldet, rechnung):  # noqa: F811
    antwort = angemeldet.get(f"/rechnungen/{rechnung.id}/zahlungen")
    assert antwort.status_code == 302
    assert antwort.headers["Location"].endswith(f"/rechnungen/{rechnung.id}#zahlungen")


def test_zahlungsrouten_get_braucht_anmeldung(client, rechnung):  # noqa: F811
    client.post("/abmelden")  # die Fixture „rechnung“ hat den Client angemeldet
    antwort = client.get(f"/rechnungen/{rechnung.id}/zahlungen")
    assert antwort.status_code == 302 and "/anmelden" in antwort.headers["Location"]
