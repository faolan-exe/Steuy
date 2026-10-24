import pytest
from sqlalchemy import select

from app.models import Protokoll
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT, neuer_nutzer


@pytest.mark.parametrize("pfad", ["/", "/einstellungen/firma"])
def test_ohne_anmeldung_zur_anmeldung(client, admin, pfad):
    antwort = client.get(pfad)
    assert antwort.status_code == 302
    assert "/anmelden" in antwort.headers["Location"]


def test_anmeldeseite(client, admin):
    seite = client.get("/anmelden").get_data(as_text=True)
    assert "Anmelden" in seite
    assert "Musterwerkstatt" in seite


def test_anmeldung_erfolgreich_und_protokolliert(client, admin, session):
    antwort = client.post("/anmelden", data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT})
    assert antwort.status_code == 302
    assert client.get("/").status_code == 200
    eintrag = session.execute(select(Protokoll).where(Protokoll.aktion == "anmeldung")).scalar_one()
    assert eintrag.nutzer_id == admin.id


def test_email_gross_klein_egal(client, admin):
    antwort = client.post(
        "/anmelden", data={"email": " ERIKA@musterwerkstatt.example", "passwort": ADMIN_PASSWORT}
    )
    assert antwort.status_code == 302


@pytest.mark.parametrize(
    ("email", "passwort"),
    [(ADMIN_EMAIL, "falsches-passwort"), ("unbekannt@x.example", ADMIN_PASSWORT)],
)
def test_anmeldung_falsch(client, admin, session, email, passwort):
    antwort = client.post("/anmelden", data={"email": email, "passwort": passwort})
    assert antwort.status_code == 200
    assert "E-Mail oder Passwort ist falsch" in antwort.get_data(as_text=True)
    assert client.get("/").status_code == 302
    aktionen = session.execute(select(Protokoll.aktion)).scalars().all()
    assert "anmeldung_fehlgeschlagen" in aktionen


def test_deaktivierter_nutzer_kann_sich_nicht_anmelden(client, admin, session):
    neuer_nutzer(session, "weg@x.example", "buchhalter", aktiv=False)
    antwort = client.post("/anmelden", data={"email": "weg@x.example", "passwort": ADMIN_PASSWORT})
    assert antwort.status_code == 200
    assert client.get("/").status_code == 302


def test_weiterleitung_nur_auf_eigene_seiten(client, admin):
    daten = {"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT}
    antwort = client.post("/anmelden?next=https://boese.example/", data=daten)
    assert antwort.headers["Location"] == "/"
    client.post("/abmelden")
    antwort = client.post("/anmelden?next=/einstellungen/firma", data=daten)
    assert antwort.headers["Location"] == "/einstellungen/firma"


def test_abmelden(angemeldet):
    assert angemeldet.post("/abmelden").status_code == 302
    assert angemeldet.get("/").status_code == 302


def test_abmelden_nur_per_post(angemeldet):
    assert angemeldet.get("/abmelden").status_code == 405


def test_csrf_schutz_aktiv(app, admin):
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        antwort = app.test_client().post(
            "/anmelden", data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT}
        )
        assert antwort.status_code == 400
    finally:
        app.config["WTF_CSRF_ENABLED"] = False
