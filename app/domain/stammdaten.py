"""Regeln für Kontakte und Artikel ohne Datenbankbezug."""

from enum import StrEnum

KUNDENNUMMER_START = 10000
LIEFERANTENNUMMER_START = 70000


class KontaktArt(StrEnum):
    FIRMA = "firma"
    PERSON = "person"


class ArtikelTyp(StrEnum):
    PRODUKT = "produkt"
    SERVICE = "service"


EINHEITEN = (
    "Stück",
    "Stunde",
    "Tag",
    "Pauschal",
    "Kilometer",
    "Monat",
    "kg",
    "m",
    "m²",
    "Liter",
)


def naechste_nummer(bisher_hoechste: int | None, start: int) -> int:
    """Fortlaufende Nummer. Vergebene Nummern werden nie wiederverwendet."""
    return start if bisher_hoechste is None else max(bisher_hoechste + 1, start)


def anzeigename(art: str, firmenname: str | None, vorname: str | None, nachname: str | None):
    if art == KontaktArt.FIRMA:
        return firmenname or ""
    return ", ".join(teil for teil in (nachname, vorname) if teil)
