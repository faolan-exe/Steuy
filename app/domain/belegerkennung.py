"""Vorschläge für eine Buchung aus dem Text eines Belegs. Nur Vorschläge, der Nutzer prüft."""

import re
from dataclasses import dataclass
from datetime import date

from app.domain.geld import GeldFormatFehler, euro_zu_cent


@dataclass
class Vorschlag:
    quelle: str
    lieferant: str | None = None
    datum: date | None = None
    belegnummer: str | None = None
    betrag_cent: int | None = None
    hinweis: str | None = None


_BETRAG = (
    r"(-?\d{1,3}(?:[.\s]\d{3})+,\d{2}(?!\d)"  # 1.234,56
    r"|-?\d{1,3}(?:,\d{3})+\.\d{2}(?!\d)"  # 1,234.56
    r"|-?\d+,\d{2}(?!\d)"  # 12,50
    r"|-?\d+\.\d{2}(?!\d))"  # 12.50
)
_SUMMEN = [
    "gesamtbetrag",
    "rechnungsbetrag",
    "zu zahlen",
    "zahlbetrag",
    "endbetrag",
    "gesamtsumme",
    "bruttobetrag",
    "summe",
    "total",
    "betrag",
]
_MONATE = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}  # fmt: skip
_DATUM = re.compile(
    r"(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<j>\d{4}|\d{2})(?!\d)"
    r"|(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|(?P<d2>\d{1,2})\.\s*(?P<monat>" + "|".join(_MONATE) + r")\s+(?P<j2>\d{4})",
    re.IGNORECASE,
)
_NUMMER = re.compile(
    r"(?:rechnungs?[\s-]*(?:nr|nummer|no)\.?|rechnung\s+nr\.?|beleg[\s-]*(?:nr|nummer)\.?"
    r"|invoice\s*(?:no|number|nr|#)\.?|bestell[\s-]*nr\.?)\s*[:#]?\s*"
    r"(?P<nr>[A-Z0-9][A-Z0-9\-/_.]{2,30})",
    re.IGNORECASE,
)
_FIRMA = re.compile(
    r"\b(GmbH|AG|UG|KG|OHG|e\.\s?K\.|GbR|Ltd\.?|Limited|Inc\.?|S\.à\s?r\.l\.|SE|B\.V\.|S\.A\.)(?=\W|$)"
)


def _betrag(text: str) -> int | None:
    roh = re.sub(r"(?<=\d)\s(?=\d{3}\b)", ".", text)
    try:
        return euro_zu_cent(roh)
    except GeldFormatFehler:
        return None


def _datum(treffer: re.Match) -> date | None:
    try:
        if treffer.group("iso"):
            return date.fromisoformat(treffer.group("iso"))
        if treffer.group("monat"):
            return date(
                int(treffer.group("j2")),
                _MONATE[treffer.group("monat").lower()],
                int(treffer.group("d2")),
            )
        jahr = int(treffer.group("j"))
        jahr = jahr + 2000 if jahr < 100 else jahr
        return date(jahr, int(treffer.group("m")), int(treffer.group("d")))
    except ValueError:
        return None


def finde_betrag(text: str) -> int | None:
    zeilen = text.lower().splitlines()
    for schluessel in _SUMMEN:
        for zeile in reversed(zeilen):
            if schluessel in zeile:
                rest = zeile[zeile.index(schluessel) + len(schluessel) :]
                treffer = re.findall(_BETRAG, rest)
                if treffer:
                    betrag = _betrag(treffer[-1])
                    if betrag is not None:
                        return betrag
    alle = [
        b for b in (_betrag(t) for t in re.findall(_BETRAG + r"\s*(?:€|eur)", text.lower())) if b
    ]
    return max(alle) if alle else None


def finde_datum(text: str) -> date | None:
    for zeile in text.splitlines():
        if re.search(r"(rechnungs|beleg)?datum|date", zeile, re.IGNORECASE):
            for treffer in _DATUM.finditer(zeile):
                if gefunden := _datum(treffer):
                    return gefunden
    for treffer in _DATUM.finditer(text):
        if gefunden := _datum(treffer):
            return gefunden
    return None


def finde_nummer(text: str) -> str | None:
    treffer = _NUMMER.search(text)
    if not treffer:
        return None
    nummer = treffer.group("nr").rstrip(".")
    return nummer if any(z.isdigit() for z in nummer) else None


def finde_lieferant(text: str) -> str | None:
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    for zeile in zeilen[:25]:
        if _FIRMA.search(zeile) and len(zeile) <= 80:
            return zeile.split(" · ")[0].split(" - ")[0].strip(" ,")
    for zeile in zeilen[:5]:
        buchstaben = sum(z.isalpha() for z in zeile)
        if len(zeile) <= 60 and buchstaben >= len(zeile) / 2:
            return zeile
    return None


def aus_text(text: str, quelle: str = "text") -> Vorschlag:
    return Vorschlag(
        quelle=quelle,
        lieferant=finde_lieferant(text),
        datum=finde_datum(text),
        belegnummer=finde_nummer(text),
        betrag_cent=finde_betrag(text),
    )
