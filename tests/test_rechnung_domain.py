from datetime import date

import pytest

from app.domain.epc import EpcFehler, epc_payload
from app.domain.iban import IbanFehler, formatiere_iban, pruefe_iban
from app.domain.rechnung import (
    MengenFehler,
    Position,
    RabattFehler,
    faellig_am,
    fehlende_pflichtangaben,
    formatiere_nummer,
    menge_als_text,
    menge_zu_tausendstel,
    positionsbetrag,
    rabatt_zu_basispunkten,
    summe,
)


@pytest.mark.parametrize(
    ("text", "tausendstel"),
    [("1", 1000), ("1,5", 1500), ("0,25", 250), ("2.5", 2500), ("1.000", 1_000_000), ("0,001", 1)],
)
def test_menge(text, tausendstel):
    assert menge_zu_tausendstel(text) == tausendstel


@pytest.mark.parametrize("text", ["", "abc", "1,0001", "-1", "0", "1,2,3"])
def test_menge_ungueltig(text):
    with pytest.raises(MengenFehler):
        menge_zu_tausendstel(text)


@pytest.mark.parametrize(
    ("tausendstel", "text"), [(1000, "1"), (1500, "1,5"), (250, "0,25"), (1_000_000, "1.000")]
)
def test_menge_als_text(tausendstel, text):
    assert menge_als_text(tausendstel) == text


@pytest.mark.parametrize(
    ("text", "bp"), [("", 0), ("0", 0), ("10", 1000), ("12,5", 1250), ("100", 10000)]
)
def test_rabatt(text, bp):
    assert rabatt_zu_basispunkten(text) == bp


@pytest.mark.parametrize("text", ["-5", "101", "abc", "1,234"])
def test_rabatt_ungueltig(text):
    with pytest.raises(RabattFehler):
        rabatt_zu_basispunkten(text)


@pytest.mark.parametrize(
    ("preis", "menge", "rabatt", "betrag"),
    [
        (6500, 1000, 0, 6500),
        (6500, 2500, 0, 16250),
        (60, 37_000, 0, 2220),  # 37 km à 0,60 €
        (1999, 3000, 1000, 5397),  # 59,97 € minus 10 % = 53,973 → 53,97
        (1, 1500, 0, 2),  # 1,5 Cent → kaufmännisch 2 Cent
        (1, 500, 0, 1),  # 0,5 Cent → 1 Cent
        (-5000, 1000, 0, -5000),  # Rabatt-Artikel
        (-1, 1500, 0, -2),  # negativ symmetrisch gerundet
        (12345, 1000, 10000, 0),  # 100 % Rabatt
    ],
)
def test_positionsbetrag_kaufmaennisch_gerundet(preis, menge, rabatt, betrag):
    assert positionsbetrag(preis, menge, rabatt) == betrag


def test_summe_ignoriert_textpositionen():
    positionen = [
        Position(typ="artikel", einzelpreis_cent=6500, menge_tausendstel=2000, rabatt_bp=0),
        Position(typ="text", einzelpreis_cent=0, menge_tausendstel=0, rabatt_bp=0),
        Position(typ="artikel", einzelpreis_cent=-5000, menge_tausendstel=1000, rabatt_bp=0),
    ]
    assert summe(positionen) == 8000


@pytest.mark.parametrize(
    ("praefix", "nummer", "stellen", "text"),
    [("RE", 131, 4, "RE0131"), ("RE-2026-", 1, 4, "RE-2026-0001"), ("R", 12345, 4, "R12345")],
)
def test_nummer(praefix, nummer, stellen, text):
    assert formatiere_nummer(praefix, nummer, stellen) == text


def test_faellig_am():
    assert faellig_am(date(2026, 10, 21), 14) == date(2026, 11, 4)
    assert faellig_am(date(2026, 12, 20), 14) == date(2027, 1, 3)


VOLLSTAENDIG = {
    "absender_name": "Musterwerkstatt",
    "absender_anschrift": "Hauptstraße 1, 12345 Musterstadt",
    "empfaenger_name": "Café Sonnenschein",
    "empfaenger_anschrift": "Markt 5, 50667 Köln",
    "rechnungsdatum": date(2026, 10, 21),
    "leistung_von": date(2026, 10, 18),
    "hinweis_steuerbefreiung": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
    "positionen_mit_betrag": 1,
}


def test_pflichtangaben_vollstaendig():
    assert fehlende_pflichtangaben(**VOLLSTAENDIG) == []


@pytest.mark.parametrize(
    ("feld", "meldung"),
    [
        ("empfaenger_name", "Empfänger"),
        ("empfaenger_anschrift", "Anschrift des Empfängers"),
        ("absender_anschrift", "Deine Anschrift"),
        ("rechnungsdatum", "Rechnungsdatum"),
        ("leistung_von", "Liefer- oder Leistungsdatum"),
        ("hinweis_steuerbefreiung", "Hinweis auf die Steuerbefreiung"),
        ("positionen_mit_betrag", "mindestens eine Position"),
    ],
)
def test_pflichtangaben_fehlen(feld, meldung):
    daten = {**VOLLSTAENDIG, feld: None if feld != "positionen_mit_betrag" else 0}
    fehlend = fehlende_pflichtangaben(**daten)
    assert any(meldung in f for f in fehlend)


def test_hinweis_muss_paragraf_19_nennen():
    daten = {**VOLLSTAENDIG, "hinweis_steuerbefreiung": "Steuerfrei."}
    assert any("§ 19" in f for f in fehlende_pflichtangaben(**daten))


# ---------- IBAN ----------


@pytest.mark.parametrize(
    "iban", ["DE89370400440532013000", "de89 3704 0044 0532 0130 00", "AT611904300234573201"]
)
def test_iban_gueltig(iban):
    assert pruefe_iban(iban) == iban.replace(" ", "").upper()


@pytest.mark.parametrize(
    "iban", ["", "DE89370400440532013001", "DE8937040044053201300", "XX00123", "DE89-3704"]
)
def test_iban_ungueltig(iban):
    with pytest.raises(IbanFehler):
        pruefe_iban(iban)


def test_iban_formatieren():
    assert formatiere_iban("DE89370400440532013000") == "DE89 3704 0044 0532 0130 00"


# ---------- EPC-QR (GiroCode) ----------


def test_epc_payload():
    payload = epc_payload(
        name="Musterwerkstatt",
        iban="DE89370400440532013000",
        bic="COBADEFFXXX",
        betrag_cent=123450,
        verwendungszweck="RE0131",
    )
    assert payload.split("\n") == [
        "BCD",
        "002",
        "1",
        "SCT",
        "COBADEFFXXX",
        "Musterwerkstatt",
        "DE89370400440532013000",
        "EUR1234.50",
        "",
        "",
        "RE0131",
    ]


def test_epc_ohne_bic_und_kleinbetrag():
    payload = epc_payload(
        name="X", iban="DE89370400440532013000", bic=None, betrag_cent=1, verwendungszweck="R1"
    )
    zeilen = payload.split("\n")
    assert zeilen[4] == ""
    assert zeilen[7] == "EUR0.01"


@pytest.mark.parametrize("betrag", [0, -100, 100_000_000_000])
def test_epc_betrag_ausserhalb(betrag):
    with pytest.raises(EpcFehler):
        epc_payload(
            name="X",
            iban="DE89370400440532013000",
            bic=None,
            betrag_cent=betrag,
            verwendungszweck="R1",
        )


def test_epc_kuerzt_lange_namen_und_zwecke():
    payload = epc_payload(
        name="N" * 100,
        iban="DE89370400440532013000",
        bic=None,
        betrag_cent=100,
        verwendungszweck="Z" * 200,
    )
    zeilen = payload.split("\n")
    assert len(zeilen[5]) == 70
    assert len(zeilen[10]) == 140
    assert len(payload.encode()) <= 331
