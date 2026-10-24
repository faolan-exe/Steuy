# ruff: noqa: F811  (Fixtures werden importiert und als Parameter genutzt)
import pytest

from app.services.kontakte import lege_kontakt_an
from app.services.suche import MIN_ZEICHEN, suche
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_euer import ausgabe
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401


def test_zu_kurze_suche_findet_nichts(admin):
    assert not any(suche("a").values()) and not any(suche("").values())
    assert MIN_ZEICHEN == 2


def test_findet_kontakt_rechnung_und_betrag(rechnung, admin):  # noqa: F811
    name = rechnung.empfaenger_name
    treffer = suche(name[:5])
    assert rechnung.kontakt in treffer["kontakte"] and rechnung in treffer["rechnungen"]
    # Rechnungsnummer und Betrag in deutscher Schreibweise
    assert rechnung in suche(rechnung.nummer)["rechnungen"]
    betrag = f"{rechnung.summe_cent // 100},{rechnung.summe_cent % 100:02d}"
    assert rechnung in suche(betrag)["rechnungen"]


def test_findet_buchungen_nach_partner_nummer_und_betrag(session, admin):
    buchung = ausgabe(session, admin, "Software und Abos", 4990)
    assert buchung in suche("Lieferant Software")["buchungen"]
    assert buchung in suche("49,90")["buchungen"]
    assert buchung in suche("49.90 €")["buchungen"]


def test_jahreszahl_ist_kein_betrag(session, admin):
    """Eine reine Zahl wie 2026 darf nicht als Cent-Betrag zu Zufallstreffern führen."""
    ausgabe(session, admin, "Software und Abos", 202600)
    assert suche("2026")["buchungen"] == []


def test_entwurf_ohne_nummer_wird_gefunden_nummernloses_nicht(admin, session):
    from app.services.rechnungen import neuer_entwurf

    entwurf = neuer_entwurf(admin.id)
    entwurf.empfaenger_name = "Suchtest GmbH"
    session.commit()
    assert entwurf in suche("Suchtest")["rechnungen"]


def test_sonderzeichen_brechen_die_suche_nicht(admin):
    for text in ["%", "_", "'; DROP TABLE kontakt; --", "ä ö ü ß", "\\"]:
        suche(text)  # darf nicht werfen
    lege_kontakt_an({"art": "firma", "firmenname": "Müller & Söhne", "typ": "kunde"}, admin.id)
    assert suche("Müller")["kontakte"]


def test_seite_und_kopfleiste(angemeldet, rechnung):  # noqa: F811
    assert 'href="/suche"' in angemeldet.get("/").get_data(as_text=True)
    seite = angemeldet.get(f"/suche?q={rechnung.nummer}").get_data(as_text=True)
    assert rechnung.nummer in seite and "Rechnungen und Angebote" in seite
    leer = angemeldet.get("/suche?q=gibtesnicht").get_data(as_text=True)
    assert "Nichts gefunden" in leer
    assert "mindestens 2 Zeichen" in angemeldet.get("/suche?q=a").get_data(as_text=True)
    assert angemeldet.get("/suche").status_code == 200


def test_eingabe_wird_escaped(angemeldet):
    seite = angemeldet.get("/suche?q=<script>alert(1)</script>").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in seite and "&lt;script&gt;" in seite


@pytest.mark.parametrize("rolle", ["mitarbeiter", "steuerberater"])
def test_jede_rolle_darf_suchen(client, admin, session, rolle):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/suche?q=test").status_code == 200


def test_ohne_anmeldung_umgeleitet(client, admin):
    assert client.get("/suche?q=test").status_code == 302
