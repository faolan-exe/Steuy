from datetime import date, timedelta

from app.domain.motivation import naechster_meilenstein, spruch
from app.services.zahlungen import erfasse_zahlung, rechnungsstand
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()


def test_meilensteine():
    assert [naechster_meilenstein(n) for n in (0, 1, 4, 5, 24, 25, 1000)] == [
        1,
        5,
        5,
        10,
        25,
        50,
        1100,
    ]


def test_spruch_nennt_anzahl_und_ziel():
    s = spruch(
        gesamt=10,
        bezahlt=8,
        offen=2,
        ueberfaellig=0,
        einnahmen_cent=123400,
        jahr=2026,
        heute=date(2026, 1, 1),
    )
    assert s["ziel"] == 25 and s["noch"] == 15 and 0 <= s["fortschritt"] <= 100
    alle = {
        spruch(
            gesamt=10,
            bezahlt=8,
            offen=2,
            ueberfaellig=1,
            einnahmen_cent=123400,
            jahr=2026,
            heute=date(2026, 1, tag),
        )["text"]
        for tag in range(1, 29)
    }
    assert "Du hast schon 10 Rechnungen geschrieben. Super!" in alle
    assert any("1.234 €" in t for t in alle)
    assert any("überfällig" in t for t in alle)


def test_spruch_ohne_rechnungen():
    s = spruch(
        gesamt=0, bezahlt=0, offen=0, ueberfaellig=0, einnahmen_cent=0, jahr=2026, heute=HEUTE
    )
    assert s["fortschritt"] == 0 and s["ziel"] == 1 and "erste rechnung" in s["text"].lower()


def test_rechnungsstand_offen_bezahlt_ueberfaellig(rechnung, admin, app):  # noqa: F811
    with app.app_context():
        stand = rechnungsstand(HEUTE.year)
        assert (stand["gesamt"], stand["offen"], stand["bezahlt"], stand["ueberfaellig"]) == (
            1,
            1,
            0,
            0,
        )
        spaeter = HEUTE + timedelta(days=60)
        assert rechnungsstand(HEUTE.year, heute=spaeter)["ueberfaellig"] == 1
        erfasse_zahlung(
            rechnung,
            datum=HEUTE,
            betrag_cent=rechnung.summe_cent,
            zahlungsart="bar",
            angekommen_cent=None,
            notiz=None,
            nutzer_id=admin.id,
        )
        stand = rechnungsstand(HEUTE.year, heute=spaeter)
        assert (stand["bezahlt"], stand["ueberfaellig"], stand["offen"]) == (1, 0, 0)
        assert rechnungsstand(HEUTE.year - 1)["gesamt"] == 0
        assert rechnungsstand(HEUTE.year - 1)["gesamt_alle"] == 1


def test_dashboard_zeigt_kreis_und_ziel(angemeldet, rechnung):  # noqa: F811
    seite = angemeldet.get("/").get_data(as_text=True)
    assert 'class="kreis"' in seite and "kreis-legende" in seite
    assert "Bezahlt" in seite and "Noch offen" in seite and "Überfällig" in seite
    assert "Dein Ziel" in seite and "bis zur 5. Rechnung" in seite


def test_ziel_logik():
    from app.domain.motivation import ziel_stand

    z = ziel_stand("umsatz", 1000000, 250000)
    assert (z["erreicht"], z["fortschritt"]) == (False, 25) and "7.500 €" in z["noch_text"]
    assert ziel_stand("umsatz", 1000000, 1000000)["erreicht"]
    assert ziel_stand("auftraege", 25, 30)["fortschritt"] == 100
    assert ziel_stand("auftraege", 25, 24)["fortschritt"] == 96
    assert ziel_stand("gewinn", 500000, -20000)["fortschritt"] == 0


def test_ziel_anpassen_und_glanz(angemeldet, rechnung, session):  # noqa: F811
    from app.models import Gewerbe

    seite = angemeldet.get("/").get_data(as_text=True)
    assert (
        "Ziel anpassen" in seite
        and "erreicht" not in seite.split('class="karte motivation')[1][:12]
    )
    antwort = angemeldet.post("/ziel", data={"art": "auftraege", "wert": "25"})
    assert antwort.status_code == 302
    gewerbe = session.get(Gewerbe, 1)
    assert (gewerbe.ziel_art, gewerbe.ziel_wert) == ("auftraege", 25)
    assert "bis zu 25 abgeschlossenen" in angemeldet.get("/").get_data(as_text=True)
    angemeldet.post("/ziel", data={"art": "umsatz", "wert": "12,50"})
    assert session.get(Gewerbe, 1).ziel_wert == 1250
    erreicht = angemeldet.get("/").get_data(as_text=True)
    assert "karte motivation" in erreicht and "Noch" in erreicht
    angemeldet.post("/ziel", data={"art": "gewinn", "wert": "abc"})
    assert session.get(Gewerbe, 1).ziel_art == "umsatz"
    angemeldet.post("/ziel", data={"aktion": "entfernen"})
    assert session.get(Gewerbe, 1).ziel_art is None


def test_ziel_erreicht_laesst_kasten_glaenzen(angemeldet, rechnung, admin, session, app):  # noqa: F811
    from app.models import Gewerbe
    from app.services.zahlungen import erfasse_zahlung

    angemeldet.post("/ziel", data={"art": "auftraege", "wert": "1"})
    assert "motivation erreicht" not in angemeldet.get("/").get_data(as_text=True)
    with app.app_context():
        erfasse_zahlung(
            rechnung,
            datum=HEUTE,
            betrag_cent=rechnung.summe_cent,
            zahlungsart="bar",
            angekommen_cent=None,
            notiz=None,
            nutzer_id=admin.id,
        )
    seite = angemeldet.get("/").get_data(as_text=True)
    assert "motivation erreicht" in seite and "Ziel erreicht" in seite and "Geschafft!" in seite
    assert session.get(Gewerbe, 1).ziel_art == "auftraege"


def test_ziel_braucht_einstellungsrecht(client, admin, session):
    from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

    neuer_nutzer(session, "mitarbeiter@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "mitarbeiter@x.example", "passwort": ADMIN_PASSWORT})
    assert client.post("/ziel", data={"art": "umsatz", "wert": "5"}).status_code == 403


def test_jahreswahl_nur_jahre_mit_daten(angemeldet, rechnung, admin, session, app):  # noqa: F811
    from app.services.buchungen import Buchungsdaten, lege_entwurf_an
    from app.services.zahlungen import jahre_mit_daten

    with app.app_context():
        assert jahre_mit_daten() == [HEUTE.year]
        lege_entwurf_an(
            Buchungsdaten(
                art="ausgabe",
                belegdatum=date(HEUTE.year - 3, 5, 1),
                betrag_cent=100,
                kategorie_id=None,
            ),
            admin.id,
        )
        assert jahre_mit_daten() == [HEUTE.year, HEUTE.year - 3]
    seite = angemeldet.get("/").get_data(as_text=True)
    assert f'value="{HEUTE.year - 3}"' in seite and f'value="{HEUTE.year - 1}"' not in seite
    fremd = angemeldet.get(f"/?jahr={HEUTE.year - 1}").get_data(as_text=True)
    assert f'value="{HEUTE.year}" selected' in fremd  # Jahr ohne Daten: zurück auf aktuell
