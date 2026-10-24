import pytest
from sqlalchemy import select

from app.models import Artikel, Protokoll
from app.services.artikel import ArtikelnummerVergeben, lege_artikel_an, suche_artikel
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

DJ = {
    "typ": "service",
    "bezeichnung": "Auftritt pro Stunde",
    "beschreibung": "Musik mit eigener Technik",
    "einheit": "Stunde",
    "preis": "65,00",
}
KABEL = {
    "typ": "produkt",
    "bezeichnung": "Kabel 5 m",
    "artikelnummer": "K-005",
    "gtin": "4006381333931",
    "einheit": "Stück",
    "preis": "1.234,50",
}


def test_anlegen_ueber_formular(angemeldet, session):
    antwort = angemeldet.post("/artikel/neu", data=KABEL)
    assert antwort.status_code == 302
    artikel = session.execute(select(Artikel)).scalar_one()
    assert artikel.preis_cent == 123450
    assert artikel.artikelnummer == "K-005"
    aktionen = session.execute(select(Protokoll.aktion)).scalars().all()
    assert "artikel_angelegt" in aktionen


def test_negativer_preis_erlaubt(angemeldet, session):
    daten = {**DJ, "bezeichnung": "Rabatt", "einheit": "Pauschal", "preis": "-50,00"}
    assert angemeldet.post("/artikel/neu", data=daten).status_code == 302
    assert session.execute(select(Artikel.preis_cent)).scalar_one() == -5000


@pytest.mark.parametrize(
    ("aenderung", "meldung"),
    [
        ({"preis": "abc"}, "Ungültiger Betrag"),
        ({"preis": "12,345"}, "Mehrdeutiger Betrag"),
        ({"preis": ""}, "Pflichtfeld"),
        ({"bezeichnung": ""}, "Pflichtfeld"),
        ({"gtin": "123"}, "8, 12, 13 oder 14 Ziffern"),
        ({"einheit": "Fass"}, "Bitte aus der Liste wählen"),
    ],
)
def test_formular_prueft(angemeldet, session, aenderung, meldung):
    antwort = angemeldet.post("/artikel/neu", data={**KABEL, **aenderung})
    assert antwort.status_code == 200
    assert meldung in antwort.get_data(as_text=True)
    assert session.execute(select(Artikel)).first() is None


def test_artikelnummer_eindeutig(angemeldet, admin):
    lege_artikel_an({**KABEL, "preis_cent": 100}, admin.id)
    antwort = angemeldet.post("/artikel/neu", data=KABEL)
    assert "bereits vergeben" in antwort.get_data(as_text=True)
    with pytest.raises(ArtikelnummerVergeben):
        lege_artikel_an({**KABEL, "preis_cent": 100}, admin.id)


def test_leere_artikelnummer_mehrfach_erlaubt(admin):
    lege_artikel_an({**DJ, "preis_cent": 6500}, admin.id)
    lege_artikel_an({**DJ, "bezeichnung": "Zweiter", "preis_cent": 6500}, admin.id)
    assert len(suche_artikel("")) == 2


def test_liste_filter_und_suche(angemeldet, admin):
    lege_artikel_an({**DJ, "preis_cent": 6500}, admin.id)
    lege_artikel_an({**KABEL, "preis_cent": 999}, admin.id)
    seite = angemeldet.get("/artikel?filter=services").get_data(as_text=True)
    assert "Auftritt pro Stunde" in seite and "Kabel 5 m" not in seite
    assert "65,00 €" in seite
    assert [a.bezeichnung for a in suche_artikel("k-005")] == ["Kabel 5 m"]
    assert [a.bezeichnung for a in suche_artikel("technik")] == ["Auftritt pro Stunde"]


def test_bearbeiten_und_archivieren(angemeldet, admin):
    artikel = lege_artikel_an({**DJ, "preis_cent": 6500}, admin.id)
    seite = angemeldet.get(f"/artikel/{artikel.id}/bearbeiten").get_data(as_text=True)
    assert 'value="65,00"' in seite
    angemeldet.post(f"/artikel/{artikel.id}/bearbeiten", data={**DJ, "preis": "70"})
    assert artikel.preis_cent == 7000
    angemeldet.post(f"/artikel/{artikel.id}/archivieren")
    assert artikel.archiviert
    assert suche_artikel("") == []


def test_steuerberater_nur_lesen(client, admin, session):
    artikel = lege_artikel_an({**DJ, "preis_cent": 6500}, admin.id)
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    client.post("/anmelden", data={"email": "stb@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/artikel").status_code == 200
    assert client.get("/artikel/neu").status_code == 403
    assert client.post(f"/artikel/{artikel.id}/bearbeiten", data=DJ).status_code == 403
    assert client.post(f"/artikel/{artikel.id}/archivieren").status_code == 403
