import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import Kontakt, Protokoll
from app.services.kontakte import aendere_kontakt, lege_kontakt_an, setze_archiviert, suche_kontakte
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

FIRMA = {
    "art": "firma",
    "firmenname": "Café Sonnenschein",
    "typ": "kunde",
    "strasse": "Markt 5",
    "plz": "50667",
    "ort": "Köln",
    "land": "Deutschland",
    "email": "hallo@cafe.example",
}
PERSON = {
    "art": "person",
    "vorname": "Jonas",
    "nachname": "Weber",
    "typ": "kunde",
    "plz": "20095",
    "ort": "Hamburg",
    "land": "Deutschland",
}


def anlegen(daten, admin, **mehr):
    return lege_kontakt_an({**daten, **mehr}, admin.id)


def test_kundennummern_fortlaufend_ab_10000(admin):
    erster = anlegen(FIRMA, admin)
    zweiter = anlegen(PERSON, admin)
    assert (erster.kundennummer, zweiter.kundennummer) == (10000, 10001)
    assert erster.lieferantennummer is None


def test_lieferant_und_beides(admin):
    lieferant = anlegen(FIRMA, admin, typ="lieferant")
    beides = anlegen(PERSON, admin, typ="beides")
    assert lieferant.lieferantennummer == 70000
    assert lieferant.kundennummer is None
    assert (beides.kundennummer, beides.lieferantennummer) == (10000, 70001)


def test_nummern_werden_nie_wiederverwendet(admin):
    erster = anlegen(FIRMA, admin)
    setze_archiviert(erster, True, admin.id)
    assert anlegen(PERSON, admin).kundennummer == 10001


def test_lieferant_wird_auch_kunde(admin):
    kontakt = anlegen(FIRMA, admin, typ="lieferant")
    aendere_kontakt(kontakt, {**FIRMA, "typ": "beides"}, admin.id)
    assert kontakt.kundennummer == 10000
    assert kontakt.lieferantennummer == 70000


def test_kunde_hoert_auf_nummer_bleibt(admin):
    kontakt = anlegen(FIRMA, admin, typ="beides")
    aendere_kontakt(kontakt, {**FIRMA, "typ": "lieferant"}, admin.id)
    assert not kontakt.ist_kunde
    assert kontakt.kundennummer == 10000


def test_anzeigename():
    assert Kontakt(art="person", vorname="Jonas", nachname="Weber").name == "Weber, Jonas"
    assert Kontakt(art="person", nachname="Weber").name == "Weber"
    assert Kontakt(art="firma", firmenname="ACME").name == "ACME"


def test_protokoll_ohne_personendaten(admin, session):
    kontakt = anlegen(PERSON, admin)
    aendere_kontakt(kontakt, {**PERSON, "ort": "Bremen", "plz": "28195"}, admin.id)
    eintraege = session.execute(
        select(Protokoll).where(Protokoll.objekt_typ == "kontakt").order_by(Protokoll.id)
    ).scalars()
    eintraege = list(eintraege)
    assert [e.aktion for e in eintraege] == ["kontakt_angelegt", "kontakt_geaendert"]
    assert eintraege[1].details == {"felder": ["ort", "plz"]}
    assert "Bremen" not in str(eintraege[1].details)


def test_suche(admin):
    anlegen(FIRMA, admin)
    anlegen(PERSON, admin, typ="lieferant")
    assert [k.name for k in suche_kontakte("sonnen")] == ["Café Sonnenschein"]
    assert [k.name for k in suche_kontakte("10000")] == ["Café Sonnenschein"]
    assert [k.name for k in suche_kontakte("hamburg")] == ["Weber, Jonas"]
    assert [k.name for k in suche_kontakte("", filter="lieferanten")] == ["Weber, Jonas"]
    assert [k.name for k in suche_kontakte("", filter="kunden")] == ["Café Sonnenschein"]


def test_archivierte_nur_auf_wunsch(admin):
    kontakt = anlegen(FIRMA, admin)
    setze_archiviert(kontakt, True, admin.id)
    assert suche_kontakte("") == []
    assert suche_kontakte("", archiv=True) == [kontakt]


def test_db_kontakt_braucht_typ(admin, session):
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(text("INSERT INTO kontakt (art, firmenname) VALUES ('firma', 'X')"))


# ---------- Oberfläche ----------


def test_liste_und_reiter(angemeldet, admin):
    anlegen(FIRMA, admin)
    anlegen(PERSON, admin, typ="lieferant")
    alle = angemeldet.get("/kontakte").get_data(as_text=True)
    assert "Café Sonnenschein" in alle and "Weber, Jonas" in alle
    kunden = angemeldet.get("/kontakte?filter=kunden").get_data(as_text=True)
    assert "Café Sonnenschein" in kunden and "Weber, Jonas" not in kunden


def test_suche_per_htmx_liefert_nur_tabellenzeilen(angemeldet, admin):
    anlegen(FIRMA, admin)
    antwort = angemeldet.get("/kontakte?q=sonnen", headers={"HX-Request": "true"})
    seite = antwort.get_data(as_text=True)
    assert "Café Sonnenschein" in seite
    assert "<html" not in seite


def test_anlegen_ueber_formular(angemeldet, session):
    antwort = angemeldet.post("/kontakte/neu", data=FIRMA)
    assert antwort.status_code == 302
    kontakt = session.execute(select(Kontakt)).scalar_one()
    assert antwort.headers["Location"].endswith(f"/kontakte/{kontakt.id}")
    assert kontakt.kundennummer == 10000


@pytest.mark.parametrize(
    ("daten", "meldung"),
    [
        ({**FIRMA, "firmenname": ""}, "Firmenname fehlt"),
        ({**PERSON, "nachname": ""}, "Nachname fehlt"),
        ({**FIRMA, "plz": "123"}, "fünfstellige Postleitzahl"),
        ({**FIRMA, "email": "kaputt"}, "gültige E-Mail-Adresse"),
        ({**FIRMA, "ust_idnr": "DE12"}, "USt-IdNr."),
    ],
)
def test_formular_prueft(angemeldet, session, daten, meldung):
    antwort = angemeldet.post("/kontakte/neu", data=daten)
    assert antwort.status_code == 200
    assert meldung in antwort.get_data(as_text=True)
    assert session.execute(select(Kontakt)).first() is None


def test_auslaendische_plz_frei(angemeldet, session):
    antwort = angemeldet.post(
        "/kontakte/neu", data={**FIRMA, "land": "Österreich", "plz": "1010", "ust_idnr": ""}
    )
    assert antwort.status_code == 302


def test_detail_bearbeiten_archivieren(angemeldet, admin, session):
    kontakt = anlegen(FIRMA, admin)
    assert "Markt 5" in angemeldet.get(f"/kontakte/{kontakt.id}").get_data(as_text=True)
    antwort = angemeldet.post(f"/kontakte/{kontakt.id}/bearbeiten", data={**FIRMA, "ort": "Bonn"})
    assert antwort.status_code == 302
    assert kontakt.ort == "Bonn"
    angemeldet.post(f"/kontakte/{kontakt.id}/archivieren")
    assert kontakt.archiviert
    angemeldet.post(f"/kontakte/{kontakt.id}/archivieren")
    assert not kontakt.archiviert


def test_unbekannter_kontakt(angemeldet):
    assert angemeldet.get("/kontakte/999999").status_code == 404


def test_steuerberater_sieht_aber_aendert_nicht(client, admin, session):
    kontakt = anlegen(FIRMA, admin)
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    client.post("/anmelden", data={"email": "stb@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/kontakte").status_code == 200
    assert client.get(f"/kontakte/{kontakt.id}").status_code == 200
    assert client.get("/kontakte/neu").status_code == 403
    assert client.post(f"/kontakte/{kontakt.id}/bearbeiten", data=FIRMA).status_code == 403
    assert client.post(f"/kontakte/{kontakt.id}/archivieren").status_code == 403


def test_mitarbeiter_darf_anlegen(client, admin, session):
    neuer_nutzer(session, "m@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "m@x.example", "passwort": ADMIN_PASSWORT})
    assert client.post("/kontakte/neu", data=FIRMA).status_code == 302
