from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.domain.jahreswechsel import anderes_jahr, im_fenster
from app.models import Jahreszuordnung, Zahlung
from app.services.buchungen import Buchungsdaten, festschreiben, lege_entwurf_an, storniere
from app.services.euer import berechne
from app.services.jahreswechsel import ZuordnungUngueltig, bestaetige, kandidaten
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_euer import kategorie_id, zeile

JAHR = date.today().year - 1  # letzter Jahreswechsel liegt sicher in der Vergangenheit


def miete(session, admin, datum, partner="Vermieter Huber", betrag=50000):
    buchung = lege_entwurf_an(
        Buchungsdaten(
            art="ausgabe",
            belegdatum=datum,
            betrag_cent=betrag,
            kategorie_id=kategorie_id(session, "Miete und Raumkosten"),
            partner=partner,
        ),
        admin.id,
    )
    festschreiben(buchung, admin.id, bezahlt_am=datum, zahlungsart="ueberweisung")
    return session.execute(select(Zahlung).where(Zahlung.buchung_id == buchung.id)).scalar_one()


@pytest.fixture
def mietzahlungen(session, admin):
    for monat in (10, 11):
        miete(session, admin, date(JAHR - 1, monat, 1))
    return miete(session, admin, date(JAHR - 1, 12, 28))


# ---------- Domain ----------


@pytest.mark.parametrize(
    ("datum", "erwartet"),
    [
        (date(2025, 12, 21), False),
        (date(2025, 12, 22), True),
        (date(2025, 12, 31), True),
        (date(2026, 1, 10), True),
        (date(2026, 1, 11), False),
    ],
)
def test_fenster(datum, erwartet):
    assert im_fenster(datum) is erwartet


def test_anderes_jahr():
    assert anderes_jahr(date(2025, 12, 28)) == 2026 and anderes_jahr(date(2026, 1, 5)) == 2025


# ---------- Erkennung ----------


def test_regelmaessige_zahlung_wird_erkannt(session, admin, mietzahlungen):
    assert kandidaten() == [mietzahlungen]


def test_einmalige_zahlung_nicht(session, admin):
    miete(session, admin, date(JAHR - 1, 12, 28), partner="Einmalig GmbH")
    assert kandidaten() == []


def test_ausserhalb_des_fensters_nicht(session, admin):
    for monat in (9, 10, 11):
        miete(session, admin, date(JAHR - 1, monat, 15))
    assert kandidaten() == []


# ---------- Zuordnung und EÜR ----------


def test_zuordnung_verschiebt_in_der_euer(session, admin, mietzahlungen):
    vorher = berechne(JAHR - 1).summe_ausgaben
    bestaetige(mietzahlungen, JAHR, admin.id)
    assert berechne(JAHR - 1).summe_ausgaben == vorher - 50000
    neu = berechne(JAHR)
    assert zeile(neu, 39)[0] == 50000
    assert "Jahreswechsel" in zeile(neu, 39)[1][0].text
    assert kandidaten() == []


def test_bleibt_im_zahlungsjahr(session, admin, mietzahlungen):
    vorher = berechne(JAHR - 1).summe_ausgaben
    bestaetige(mietzahlungen, JAHR - 1, admin.id)
    assert berechne(JAHR - 1).summe_ausgaben == vorher and kandidaten() == []


def test_storno_folgt_der_zuordnung(session, admin, mietzahlungen):
    bestaetige(mietzahlungen, JAHR, admin.id)
    storniere(mietzahlungen.buchung, admin.id)
    assert berechne(JAHR).summe_ausgaben == 0


def test_ungueltige_zuordnung(session, admin, mietzahlungen):
    with pytest.raises(ZuordnungUngueltig):
        bestaetige(mietzahlungen, JAHR + 3, admin.id)
    bestaetige(mietzahlungen, JAHR, admin.id)
    with pytest.raises(ZuordnungUngueltig, match="schon festgelegt"):
        bestaetige(mietzahlungen, JAHR - 1, admin.id)


def test_zuordnung_unveraenderlich(session, admin, mietzahlungen):
    bestaetige(mietzahlungen, JAHR, admin.id)
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text("UPDATE jahreszuordnung SET jahr = 2000"))


# ---------- Oberfläche ----------


def test_zu_pruefen_und_bestaetigen(angemeldet, session, admin, mietzahlungen):
    seite = angemeldet.get("/zu-pruefen").get_data(as_text=True)
    assert "Zahlungen am Jahreswechsel" in seite and f">{JAHR}</button>" in seite
    angemeldet.post(f"/jahreswechsel/{mietzahlungen.id}", data={"jahr": str(JAHR)})
    assert session.get(Jahreszuordnung, mietzahlungen.id).jahr == JAHR
    assert "Zahlungen am Jahreswechsel" not in angemeldet.get("/zu-pruefen").get_data(as_text=True)


@pytest.mark.parametrize(("rolle", "status"), [("mitarbeiter", 403), ("buchhalter", 302)])
def test_rechte(client, session, admin, mietzahlungen, rolle, status):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    antwort = client.post(f"/jahreswechsel/{mietzahlungen.id}", data={"jahr": str(JAHR)})
    assert antwort.status_code == status
