from datetime import date, timedelta

from sqlalchemy import select

from app.models import Rechnung
from app.services.kontakte import uebersicht
from app.services.rechnungen import neuer_entwurf
from app.services.zahlungen import erfasse_zahlung
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()


def test_uebersicht_offen_und_bezahlt(rechnung, admin):  # noqa: F811
    erfasse_zahlung(
        rechnung,
        datum=HEUTE,
        betrag_cent=5000,
        zahlungsart="bar",
        angekommen_cent=None,
        notiz=None,
        nutzer_id=admin.id,
    )
    u = uebersicht(rechnung.kontakt)
    assert u["rechnungen"] == [rechnung]
    assert u["offen_cent"] == rechnung.summe_cent - 5000 and u["anzahl_offen"] == 1
    assert u["umsatz_cent"] == 5000
    assert u["ueberfaellig"] == []
    assert uebersicht(rechnung.kontakt, heute=HEUTE + timedelta(days=30))["ueberfaellig"] == [
        rechnung
    ]


def test_profilseite(angemeldet, rechnung):  # noqa: F811
    seite = angemeldet.get(f"/kontakte/{rechnung.kontakt_id}").get_data(as_text=True)
    assert "Überblick" in seite and "Noch offen" in seite
    assert rechnung.nummer in seite and "152,20 €" in seite
    assert "Neue Rechnung" in seite


def test_kundenspalte_verlinkt(angemeldet, rechnung):  # noqa: F811
    link = f'href="/kontakte/{rechnung.kontakt_id}"'
    assert link in angemeldet.get("/rechnungen").get_data(as_text=True)
    assert link in angemeldet.get("/zu-pruefen").get_data(as_text=True)
    assert link in angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)


def test_neue_rechnung_mit_kunde(angemeldet, kunde, session):  # noqa: F811
    antwort = angemeldet.post("/rechnungen/neu", data={"kontakt_id": str(kunde.id)})
    assert antwort.status_code == 302
    entwurf = session.execute(select(Rechnung)).scalar_one()
    assert entwurf.kontakt_id == kunde.id
    assert entwurf.empfaenger_name == kunde.name and entwurf.empfaenger_ort == kunde.ort


def test_neue_rechnung_unbekannter_kontakt(angemeldet, session, admin):
    angemeldet.post("/rechnungen/neu", data={"kontakt_id": "999"})
    assert session.execute(select(Rechnung)).scalar_one().kontakt_id is None
    assert neuer_entwurf(admin.id).kontakt_id is None


def test_lieferant_mit_ausgaben(angemeldet, admin, session):
    from app.services.kontakte import lege_kontakt_an

    lieferant = lege_kontakt_an(
        {"art": "firma", "firmenname": "Druckerei Blau", "typ": "lieferant"}, admin.id
    )
    from app.services.buchungen import Buchungsdaten, festschreiben, lege_entwurf_an
    from tests.test_euer import kategorie_id

    buchung = lege_entwurf_an(
        Buchungsdaten(
            art="ausgabe",
            belegdatum=HEUTE,
            betrag_cent=12000,
            kategorie_id=kategorie_id(session, "Werbung"),
            kontakt_id=lieferant.id,
        ),
        admin.id,
    )
    festschreiben(buchung, admin.id, bezahlt_am=HEUTE, zahlungsart="ueberweisung")
    seite = angemeldet.get(f"/kontakte/{lieferant.id}").get_data(as_text=True)
    assert "Einnahmen und Ausgaben" in seite and "120,00 €" in seite
    assert "Neue Rechnung" not in seite


def test_mitarbeiter_sieht_profil_ohne_knopf_steuerberater(client, rechnung, session):  # noqa: F811
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    client.post("/abmelden")
    client.post("/anmelden", data={"email": "stb@x.example", "passwort": ADMIN_PASSWORT})
    seite = client.get(f"/kontakte/{rechnung.kontakt_id}").get_data(as_text=True)
    assert rechnung.nummer in seite and "Neue Rechnung" not in seite
