import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import Gewerbe, Nutzer, Protokoll
from app.services.einrichtung import BereitsEingerichtet, richte_ein
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT, FIRMENDATEN


def formular(**ueberschreiben):
    daten = {
        **FIRMENDATEN,
        "einzelunternehmen": "y",
        "umsatz_passt": "y",
        "admin_name": "Erika Mustermann",
        "admin_email": ADMIN_EMAIL,
        "passwort": ADMIN_PASSWORT,
        "passwort_wiederholen": ADMIN_PASSWORT,
    }
    daten.update(ueberschreiben)
    return {k: v for k, v in daten.items() if v is not None}


@pytest.mark.parametrize("pfad", ["/", "/anmelden", "/einstellungen/firma"])
def test_ohne_einrichtung_fuehrt_alles_zur_einrichtung(client, pfad):
    antwort = client.get(pfad)
    assert antwort.status_code == 302
    assert antwort.headers["Location"].endswith("/einrichtung")


def test_einrichtungsseite_zeigt_grenzwerte(client):
    seite = client.get("/einrichtung").get_data(as_text=True)
    assert "25.000,00 €" in seite
    assert "100.000,00 €" in seite


def test_einrichtung_legt_gewerbe_admin_und_protokoll_an(client, session):
    antwort = client.post("/einrichtung", data=formular())
    assert antwort.status_code == 302
    assert antwort.headers["Location"].endswith("/rundgang")

    gewerbe = session.get(Gewerbe, 1)
    assert gewerbe.name == "Musterwerkstatt"
    assert gewerbe.telefon is None  # leere Felder werden NULL

    admin = session.execute(select(Nutzer)).scalar_one()
    assert admin.rolle == "admin"
    assert admin.passwort_hash != ADMIN_PASSWORT

    aktionen = session.execute(select(Protokoll.aktion)).scalars().all()
    assert "einrichtung" in aktionen

    # direkt angemeldet
    assert client.get("/").status_code == 200


def test_email_wird_normalisiert(client, session):
    client.post("/einrichtung", data=formular(admin_email="  Erika@Musterwerkstatt.EXAMPLE "))
    assert session.execute(select(Nutzer.email)).scalar_one() == ADMIN_EMAIL


@pytest.mark.parametrize("feld", ["einzelunternehmen", "umsatz_passt"])
def test_ohne_kleinunternehmer_voraussetzung_keine_einrichtung(client, session, feld):
    antwort = client.post("/einrichtung", data=formular(**{feld: None}))
    assert antwort.status_code == 200
    assert "nur für Kleinunternehmer" in antwort.get_data(as_text=True)
    assert session.get(Gewerbe, 1) is None


@pytest.mark.parametrize(
    ("aenderung", "meldung"),
    [
        ({"passwort": "kurz", "passwort_wiederholen": "kurz"}, "mindestens 10 Zeichen"),
        ({"passwort_wiederholen": "etwas-anderes-123"}, "stimmen nicht überein"),
        ({"admin_email": "keine-email"}, "gültige E-Mail-Adresse"),
        ({"plz": "1234"}, "fünfstellige Postleitzahl"),
        ({"name": ""}, "Pflichtfeld"),
    ],
)
def test_einrichtung_prueft_eingaben(client, session, aenderung, meldung):
    antwort = client.post("/einrichtung", data=formular(**aenderung))
    assert antwort.status_code == 200
    assert meldung in antwort.get_data(as_text=True)
    assert session.get(Gewerbe, 1) is None


def test_einrichtung_nur_einmal(client, admin):
    assert client.get("/einrichtung").status_code == 404
    assert (
        client.post("/einrichtung", data=formular(admin_email="neu@x.example")).status_code == 404
    )


def test_service_verhindert_zweite_einrichtung(admin):
    with pytest.raises(BereitsEingerichtet):
        richte_ein(dict(FIRMENDATEN), "Zweiter", "zweiter@x.example", ADMIN_PASSWORT)


def test_datenbank_erlaubt_nur_ein_gewerbe(admin, session):
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO gewerbe (id, name, inhaber, strasse, plz, ort, email) "
                "VALUES (2, 'x', 'x', 'x', '12345', 'x', 'x@x.example')"
            )
        )
