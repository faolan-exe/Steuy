from datetime import date

import pytest

from app.domain.wiederkehrend import (
    MAX_NACHHOLEN,
    TerminFehler,
    addiere_monate,
    ersetze_platzhalter,
    faellige_termine,
    naechster_termin,
    zeitraum,
)


@pytest.mark.parametrize(
    ("start", "monate", "anker", "erwartet"),
    [
        (date(2026, 1, 15), 1, 15, date(2026, 2, 15)),
        (date(2026, 1, 31), 1, 31, date(2026, 2, 28)),  # kurzer Monat
        (date(2026, 2, 28), 1, 31, date(2026, 3, 31)),  # Anker kehrt zurück
        (date(2028, 1, 31), 1, 31, date(2028, 2, 29)),  # Schaltjahr
        (date(2026, 11, 30), 3, 30, date(2027, 2, 28)),  # über den Jahreswechsel
        (date(2026, 12, 1), 1, 1, date(2027, 1, 1)),
        (date(2026, 3, 1), 12, 1, date(2027, 3, 1)),
        (date(2024, 2, 29), 12, 29, date(2025, 2, 28)),  # Schalttag im nächsten Jahr
    ],
)
def test_monate_addieren(start, monate, anker, erwartet):
    assert addiere_monate(start, monate, anker) == erwartet


def test_ankertag_verhindert_wandern_ueber_viele_monate():
    termin = date(2026, 1, 31)
    tage = []
    for _ in range(6):
        termin = naechster_termin(termin, "monatlich", 31)
        tage.append(termin.day)
    assert tage == [28, 31, 30, 31, 30, 31]


def test_unbekanntes_intervall():
    with pytest.raises(TerminFehler):
        naechster_termin(date(2026, 1, 1), "woechentlich", 1)


def test_zeitraum_endet_am_tag_vor_dem_naechsten_termin():
    assert zeitraum(date(2026, 11, 1), "monatlich", 1) == (date(2026, 11, 1), date(2026, 11, 30))
    assert zeitraum(date(2026, 1, 1), "quartalsweise", 1) == (date(2026, 1, 1), date(2026, 3, 31))
    assert zeitraum(date(2026, 1, 31), "monatlich", 31) == (date(2026, 1, 31), date(2026, 2, 27))
    assert zeitraum(date(2026, 1, 1), "jaehrlich", 1) == (date(2026, 1, 1), date(2026, 12, 31))


def test_faellige_termine_heute_und_verpasste():
    assert faellige_termine(date(2026, 11, 1), date(2026, 10, 31), "monatlich", 1) == []
    assert faellige_termine(date(2026, 11, 1), date(2026, 11, 1), "monatlich", 1) == [
        date(2026, 11, 1)
    ]
    assert faellige_termine(date(2026, 9, 1), date(2026, 11, 15), "monatlich", 1) == [
        date(2026, 9, 1),
        date(2026, 10, 1),
        date(2026, 11, 1),
    ]


def test_faellige_termine_ende_und_obergrenze():
    assert faellige_termine(
        date(2026, 9, 1), date(2026, 12, 31), "monatlich", 1, ende_am=date(2026, 10, 15)
    ) == [date(2026, 9, 1), date(2026, 10, 1)]
    assert len(faellige_termine(date(2020, 1, 1), date(2026, 1, 1), "monatlich", 1)) == (
        MAX_NACHHOLEN
    )
    assert (
        faellige_termine(date(2026, 11, 1), date(2026, 12, 1), "monatlich", 1, date(2026, 10, 1))
        == []
    )


def test_platzhalter():
    von, bis = date(2026, 3, 1), date(2026, 5, 31)
    text = "Abo {monat}, {quartal}, {jahr}: {zeitraum} ({von} - {bis}) {unbekannt}"
    assert ersetze_platzhalter(text, von, bis) == (
        "Abo März 2026, Q1 2026, 2026: 01.03.2026 bis 31.05.2026 (01.03.2026 - 31.05.2026) "
        "{unbekannt}"
    )
    assert ersetze_platzhalter(None, von, bis) is None
    assert ersetze_platzhalter("", von, bis) == ""
