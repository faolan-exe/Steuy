import re
from pathlib import Path

import pytest

from app.web.hilfe import BEGRIFFE, NACH_BESCHRIFTUNG, NACH_NAME, symbol_fuer_begriff
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

TEMPLATES = Path(__file__).parent.parent / "app" / "web" / "templates"


def test_alle_begriffe_in_templates_vorhanden():
    benutzt = set()
    for datei in TEMPLATES.rglob("*.html"):
        benutzt |= set(re.findall(r"""(?<![a-z])hilfe\(["']([a-z_]+)["']\)""", datei.read_text()))
    assert benutzt, "Keine Hilfe-Begriffe gefunden"
    assert benutzt <= set(BEGRIFFE), benutzt - set(BEGRIFFE)
    namen = set()
    for datei in TEMPLATES.rglob("*.html"):
        namen |= set(re.findall(r"""namenhilfe\(["']([a-z_]+)["']\)""", datei.read_text()))
    assert namen <= set(NACH_NAME)


def test_texte_kurz_und_ohne_html():
    for text in [*BEGRIFFE.values(), *NACH_NAME.values(), *NACH_BESCHRIFTUNG.values()]:
        assert 20 <= len(text) <= 420, text
        assert "<" not in text


def test_symbol_escaped_und_aus():
    symbol = str(symbol_fuer_begriff("euer", True))
    assert 'class="hilfe"' in symbol and 'data-hilfe="Einnahmen-Überschuss' in symbol
    assert str(symbol_fuer_begriff("euer", False)) == ""


def test_dashboard_und_formular_zeigen_hilfe(angemeldet):
    seite = angemeldet.get("/").get_data(as_text=True)
    assert 'data-hilfe="Wer im Vorjahr höchstens 25.000 €' in seite
    seite = angemeldet.get("/einstellungen/rechnungen").get_data(as_text=True)
    assert 'data-hilfe="Deine Kontonummer' in seite
    assert 'data-hilfe="So viele Tage hat dein Kunde' in seite


def test_beschriftung_vor_name(angemeldet):
    """„Betrag brutto €“ bei Ausgaben erklärt etwas anderes als „Betrag €“ bei Zahlungen."""
    seite = angemeldet.get("/buchungen/neu").get_data(as_text=True)
    assert "bekommst du die Mehrwertsteuer nicht vom Finanzamt zurück" in seite
    assert 'data-hilfe="Nutzt du etwas auch privat' in seite


def test_im_profil_abschaltbar(angemeldet, admin, session):
    seite = angemeldet.get("/profil").get_data(as_text=True)
    assert "Hilfe-Fragezeichen anzeigen" in seite and "checked" in seite

    antwort = angemeldet.post("/profil/hilfe", data={})
    assert antwort.status_code == 302
    session.refresh(admin)
    assert admin.hilfe_anzeigen is False
    assert "data-hilfe=" not in angemeldet.get("/").get_data(as_text=True)
    assert "data-hilfe=" not in angemeldet.get("/einstellungen/rechnungen").get_data(as_text=True)

    angemeldet.post("/profil/hilfe", data={"hilfe_anzeigen": "y"})
    session.refresh(admin)
    assert admin.hilfe_anzeigen is True
    assert "data-hilfe=" in angemeldet.get("/").get_data(as_text=True)


def test_einstellung_pro_person(client, angemeldet, admin, session):
    angemeldet.post("/profil/hilfe", data={})
    neuer_nutzer(session, "neu@x.example", "buchhalter")
    angemeldet.post("/abmelden")
    client.post("/anmelden", data={"email": "neu@x.example", "passwort": ADMIN_PASSWORT})
    assert "data-hilfe=" in client.get("/").get_data(as_text=True)


def test_einrichtung_mit_hilfe(client):
    seite = client.get("/einrichtung").get_data(as_text=True)
    assert 'data-hilfe="' in seite


@pytest.mark.parametrize("rolle", ["mitarbeiter", "steuerberater"])
def test_jede_rolle_darf_umschalten(client, admin, session, rolle):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.post("/profil/hilfe", data={}).status_code == 302


def test_anmeldeseite_ohne_hilfe_und_deutsch(client, admin):
    antwort = client.get("/", follow_redirects=True)
    seite = antwort.get_data(as_text=True)
    assert "Bitte melde dich an" in seite and "Please log in" not in seite
    assert "data-hilfe=" not in seite


def test_kontaktformular_erklaert_kundendaten_nicht_wie_die_eigenen(angemeldet):
    """Im Kontaktformular geht es um den Kunden, nicht um die Firmendaten."""
    kontakt = angemeldet.get("/kontakte/neu").get_data(as_text=True)
    assert "Die Rechnungsadresse deines Kunden" in kontakt
    assert "Deine Geschäftsadresse" not in kontakt
    assert "Bei deinen Firmendaten steht sie auf Rechnungen" not in kontakt
    assert "Die Umsatzsteuer-ID deines Kunden" in kontakt
    # Bei den eigenen Firmendaten bleibt es bei den bisherigen Texten
    firma = angemeldet.get("/einstellungen/firma").get_data(as_text=True)
    assert "Deine Geschäftsadresse" in firma
