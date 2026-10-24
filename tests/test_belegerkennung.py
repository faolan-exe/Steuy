from datetime import date
from pathlib import Path

import pytest

from app.domain.belegerkennung import aus_text, finde_betrag, finde_datum, finde_nummer
from app.domain.buchung import betrieblicher_anteil
from app.domain.datei import erkenne_typ
from app.domain.erechnung import ERechnungFehler, aus_xml

DATEIEN = Path(__file__).parent / "dateien"

TANKBELEG = """Muster Tankstelle GmbH
Hauptstr. 7 · 10115 Berlin
Rechnung Nr. 2026-10-77
Datum: 18.10.2026
Super E10   45,12 l   1,799 €/l
Zwischensumme 81,17 €
Gesamtbetrag 81,17 €
davon MwSt 19% 12,96 €
Vielen Dank für Ihren Einkauf
"""

AMAZON = """Amazon EU S.à r.l.
Rechnungsnummer: DE632C134AEUI
Rechnungsdatum 7. September 2026
Artikel   1   129,90 €
Versand        12,00 €
Zu zahlen   141,90 €
"""

ENGLISCH = """Software Abo Ltd
Invoice No: INV-2026-0042
Date: 2026-09-30
Total 1,234.50 EUR
"""


def test_tankbeleg():
    v = aus_text(TANKBELEG)
    assert v.lieferant == "Muster Tankstelle GmbH"
    assert v.datum == date(2026, 10, 18)
    assert v.belegnummer == "2026-10-77"
    assert v.betrag_cent == 8117


def test_amazon():
    v = aus_text(AMAZON)
    assert v.lieferant == "Amazon EU S.à r.l."
    assert v.datum == date(2026, 9, 7)
    assert v.belegnummer == "DE632C134AEUI"
    assert v.betrag_cent == 14190


def test_englisch():
    v = aus_text(ENGLISCH)
    assert v.lieferant == "Software Abo Ltd"
    assert v.datum == date(2026, 9, 30)
    assert v.belegnummer == "INV-2026-0042"
    assert v.betrag_cent == 123450


@pytest.mark.parametrize(
    ("text", "cent"),
    [
        ("Summe 1.234,56 €", 123456),
        ("Rechnungsbetrag: 1 234,56 EUR", 123456),
        ("Gesamtbetrag\n12,00\nZu zahlen 99,99", 9999),
        ("nur Beträge 5,00 € und 17,50 €", 1750),
        ("kein Betrag hier", None),
    ],
)
def test_betrag(text, cent):
    assert finde_betrag(text) == cent


@pytest.mark.parametrize(
    ("text", "datum"),
    [
        ("Lieferung 01.10.2026\nRechnungsdatum 05.10.2026", date(2026, 10, 5)),
        ("am 3.2.26 gekauft", date(2026, 2, 3)),
        ("31.02.2026 und 01.03.2026", date(2026, 3, 1)),
        ("kein Datum", None),
    ],
)
def test_datum(text, datum):
    assert finde_datum(text) == datum


def test_nummer_braucht_ziffer():
    assert finde_nummer("Rechnungsnummer: siehe unten") is None


def test_ubl():
    v = aus_xml((DATEIEN / "xrechnung_ubl.xml").read_bytes())
    assert (v.quelle, v.lieferant, v.datum, v.belegnummer, v.betrag_cent) == (
        "xrechnung",
        "Bürobedarf Muster GmbH",
        date(2026, 10, 1),
        "R-2026-0815",
        11900,
    )
    assert v.hinweis is None


def test_cii():
    v = aus_xml((DATEIEN / "zugferd_cii.xml").read_bytes())
    assert (v.lieferant, v.datum, v.belegnummer, v.betrag_cent) == (
        "Software Abo AG",
        date(2026, 9, 15),
        "INV-4711",
        1190,
    )


def test_fremdwaehrung_hinweis():
    xml = (
        (DATEIEN / "xrechnung_ubl.xml")
        .read_bytes()
        .replace(b'currencyID="EUR"', b'currencyID="USD"')
    )
    assert "USD" in aus_xml(xml).hinweis


@pytest.mark.parametrize(
    "inhalt",
    [
        b"<html><body>kein xml</body></html>",
        b"kaputt <<<",
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>',
    ],
)
def test_kein_erechnungsformat(inhalt):
    with pytest.raises(ERechnungFehler):
        aus_xml(inhalt)


@pytest.mark.parametrize(
    ("inhalt", "typ"),
    [
        (b"%PDF-1.7 ...", "application/pdf"),
        (b"\x89PNG\r\n\x1a\nabc", "image/png"),
        (b"\xff\xd8\xff\xe0abc", "image/jpeg"),
        (b"\xef\xbb\xbf<?xml version='1.0'?><a/>", "application/xml"),
        (b"MZ\x90\x00", None),
        (b"", None),
    ],
)
def test_dateityp(inhalt, typ):
    assert erkenne_typ(inhalt) == typ


@pytest.mark.parametrize(
    ("betrag", "prozent", "ergebnis"),
    [(4000, 100, 4000), (4000, 50, 2000), (999, 50, 500), (-999, 50, -500), (1234, 0, 0)],
)
def test_betrieblicher_anteil(betrag, prozent, ergebnis):
    assert betrieblicher_anteil(betrag, prozent) == ergebnis


def test_anteil_grenzen():
    with pytest.raises(ValueError):
        betrieblicher_anteil(100, 101)
