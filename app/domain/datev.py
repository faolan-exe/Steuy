"""DATEV-Buchungsstapel (Format EXTF 700, Kategorie 21) für den Wechsel zu anderer Software.

Kontenvorschläge siehe docs/domain/export.md: Sie sind ein Startpunkt für die Übernahme und
müssen von der Steuerberatung bzw. in der Zielsoftware geprüft werden.
"""

from dataclasses import dataclass
from datetime import date, datetime

SPALTEN = (
    "Umsatz (ohne Soll/Haben-Kz)",
    "Soll/Haben-Kennzeichen",
    "WKZ Umsatz",
    "Kurs",
    "Basis-Umsatz",
    "WKZ Basis-Umsatz",
    "Konto",
    "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel",
    "Belegdatum",
    "Belegfeld 1",
    "Belegfeld 2",
    "Skonto",
    "Buchungstext",
)
# Die übrigen Felder des Formats bleiben leer, DATEV erwartet aber die volle Spaltenzahl
ANZAHL_SPALTEN = 120

GELDKONTEN = {
    "SKR03": {"bank": 1200, "kasse": 1000, "privat": 1800},
    "SKR04": {"bank": 1800, "kasse": 1600, "privat": 2100},
}

# Kategorie (Name) → (SKR03, SKR04). Unbekannte Kategorien landen auf „Sonstige …“.
KONTEN = {
    "Rechnung": (8195, 4185),  # Erlöse als Kleinunternehmer i. S. d. § 19 UStG
    "Umsatzerlöse": (8195, 4185),
    "Sonstige Einnahmen": (2700, 4830),
    "Waren und Material": (3200, 5200),
    "Fremdleistungen": (3100, 5900),
    "Büromaterial": (4930, 6815),
    "Software und Abos": (4964, 6837),
    "Telefon und Internet": (4920, 6805),
    "Werbung": (4600, 6600),
    "Reisekosten": (4670, 6670),
    "Fahrzeugkosten": (4500, 6500),
    "Fortbildung": (4945, 6821),
    "Miete und Raumkosten": (4210, 6310),
    "Versicherungen und Beiträge": (4360, 6400),
    "Gebühren": (4970, 6855),
    "Geringwertige Anschaffungen": (4855, 6260),
    "Sonstige Ausgaben": (4900, 6300),
}
ERSATZ = {"einnahme": "Sonstige Einnahmen", "ausgabe": "Sonstige Ausgaben"}


class DatevUngueltig(ValueError):
    pass


@dataclass(frozen=True)
class Kopf:
    jahr: int
    kontenrahmen: str
    beraternummer: int
    mandantennummer: int
    erstellt: datetime
    bezeichnung: str = "steuy"


@dataclass(frozen=True)
class Posten:
    """Ein Geldfluss aus steuy. betrag_cent negativ = Storno/Gegenbuchung."""

    art: str  # einnahme | ausgabe
    datum: date
    betrag_cent: int
    kategorie: str | None
    zahlungsart: str
    belegfeld: str
    text: str
    betrieblich_prozent: int = 100


def pruefe_kopf(kontenrahmen: str, beraternummer: int, mandantennummer: int) -> None:
    if kontenrahmen not in GELDKONTEN:
        raise DatevUngueltig("Bitte SKR03 oder SKR04 wählen.")
    if not 1001 <= beraternummer <= 9999999:
        raise DatevUngueltig("Die Beraternummer muss zwischen 1001 und 9999999 liegen.")
    if not 1 <= mandantennummer <= 99999:
        raise DatevUngueltig("Die Mandantennummer muss zwischen 1 und 99999 liegen.")


def konto(kategorie: str | None, art: str, kontenrahmen: str) -> int:
    paar = KONTEN.get(kategorie or "") or KONTEN[ERSATZ[art]]
    return paar[0] if kontenrahmen == "SKR03" else paar[1]


def _text(wert: str, laenge: int) -> str:
    return '"' + wert.replace('"', "'").replace("\r", " ").replace("\n", " ")[:laenge] + '"'


def _betrag(cent: int) -> str:
    return f"{cent // 100},{cent % 100:02d}"


def kopfzeile(kopf: Kopf) -> list[str]:
    jahr = kopf.jahr
    return [
        '"EXTF"',
        "700",
        "21",
        '"Buchungsstapel"',
        "13",
        kopf.erstellt.strftime("%Y%m%d%H%M%S") + "000",
        "",
        '"ST"',
        "",
        "",
        str(kopf.beraternummer),
        str(kopf.mandantennummer),
        f"{jahr}0101",
        "4",
        f"{jahr}0101",
        f"{jahr}1231",
        _text(kopf.bezeichnung, 30),
        "",
        "1",
        "0",
        "0",
        '"EUR"',
        "",
        "",
        "",
        "",
        '"' + kopf.kontenrahmen[-2:] + '"',
        "",
        "",
        "",
        "",
    ]


def buchungszeilen(posten: Posten, kontenrahmen: str) -> list[list[str]]:
    """Eine Zahlung als Buchung(en): Geldkonto gegen Erlös- bzw. Aufwandskonto.

    Bei Ausgaben mit Privatanteil wird der private Teil auf das Privatkonto gebucht,
    damit das Geldkonto zum tatsächlichen Abfluss passt.
    """
    geld = GELDKONTEN[kontenrahmen]
    geldkonto = geld["kasse"] if posten.zahlungsart == "bar" else geld["bank"]
    sachkonto = konto(posten.kategorie, posten.art, kontenrahmen)
    betrieblich = posten.betrag_cent * posten.betrieblich_prozent // 100
    if posten.betrag_cent < 0:
        betrieblich = -((-posten.betrag_cent) * posten.betrieblich_prozent // 100)
    teile = [(sachkonto, betrieblich, posten.text)]
    if posten.betrag_cent - betrieblich:
        teile.append((geld["privat"], posten.betrag_cent - betrieblich, posten.text + " (privat)"))

    zeilen = []
    for gegen, cent, text in teile:
        if cent == 0:
            continue
        if posten.art == "einnahme":
            kto, gkto = geldkonto, gegen  # Soll Geldkonto an Erlös
        else:
            kto, gkto = gegen, geldkonto  # Soll Aufwand an Geldkonto
        zeile = [
            _betrag(abs(cent)),
            '"S"' if cent > 0 else '"H"',
            '"EUR"',
            "",
            "",
            "",
            str(kto),
            str(gkto),
            "",
            posten.datum.strftime("%d%m"),
            _text(posten.belegfeld, 36),
            "",
            "",
            _text(text, 60),
        ]
        zeilen.append(zeile + [""] * (ANZAHL_SPALTEN - len(zeile)))
    return zeilen


def buchungsstapel(kopf: Kopf, posten: list[Posten]) -> bytes:
    """Fertige Datei: Windows-1252, Semikolon, CRLF – wie DATEV sie erwartet."""
    if any(p.datum.year != kopf.jahr for p in posten):
        raise DatevUngueltig("Ein Buchungsstapel darf nur ein Wirtschaftsjahr enthalten.")
    namen = list(SPALTEN) + [""] * (ANZAHL_SPALTEN - len(SPALTEN))
    zeilen = [kopfzeile(kopf), namen]
    for p in sorted(posten, key=lambda p: p.datum):
        zeilen += buchungszeilen(p, kopf.kontenrahmen)
    text = "\r\n".join(";".join(z) for z in zeilen) + "\r\n"
    return text.encode("cp1252", errors="replace")
