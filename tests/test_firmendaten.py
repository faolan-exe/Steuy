import pytest
from sqlalchemy import select

from app.models import Gewerbe, Protokoll
from tests.conftest import ADMIN_PASSWORT, FIRMENDATEN, neuer_nutzer


def test_firmendaten_anzeigen(angemeldet):
    seite = angemeldet.get("/einstellungen/firma").get_data(as_text=True)
    assert "Musterwerkstatt" in seite


def test_firmendaten_aendern_mit_protokoll(angemeldet, session, admin):
    daten = {**FIRMENDATEN, "ort": "Neustadt", "telefon": "0123 456"}
    antwort = angemeldet.post("/einstellungen/firma", data=daten)
    assert antwort.status_code == 302

    gewerbe = session.get(Gewerbe, 1)
    assert gewerbe.ort == "Neustadt"

    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "firmendaten_geaendert")
    ).scalar_one()
    assert eintrag.nutzer_id == admin.id
    assert eintrag.details == {
        "ort": {"alt": "Musterstadt", "neu": "Neustadt"},
        "telefon": {"alt": None, "neu": "0123 456"},
    }


def test_ohne_aenderung_kein_protokoll(angemeldet, session):
    angemeldet.post("/einstellungen/firma", data=dict(FIRMENDATEN))
    aktionen = session.execute(select(Protokoll.aktion)).scalars().all()
    assert "firmendaten_geaendert" not in aktionen


def test_firmendaten_ungueltig(angemeldet, session):
    antwort = angemeldet.post("/einstellungen/firma", data={**FIRMENDATEN, "email": "x"})
    assert antwort.status_code == 200
    assert session.get(Gewerbe, 1).email == FIRMENDATEN["email"]


@pytest.mark.parametrize("nummer", ["abc", "12345", "12/345/67890x", "1234567890123456"])
def test_steuernummer_ungueltig(angemeldet, session, nummer):
    angemeldet.post("/einstellungen/firma", data={**FIRMENDATEN, "steuernummer": nummer})
    assert session.get(Gewerbe, 1).steuernummer == FIRMENDATEN["steuernummer"]


@pytest.mark.parametrize("nummer", ["232/123/45678", "2321234567800", "21 815 08150"])
def test_steuernummer_gueltig(angemeldet, session, nummer):
    angemeldet.post("/einstellungen/firma", data={**FIRMENDATEN, "steuernummer": nummer})
    assert session.get(Gewerbe, 1).steuernummer == nummer


@pytest.mark.parametrize("rolle", ["buchhalter", "mitarbeiter", "steuerberater"])
def test_nur_admin_darf_firmendaten_aendern(client, admin, session, rolle):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/einstellungen/firma").status_code == 403
    antwort = client.post("/einstellungen/firma", data={**FIRMENDATEN, "ort": "Anders"})
    assert antwort.status_code == 403
    assert session.get(Gewerbe, 1).ort == "Musterstadt"
