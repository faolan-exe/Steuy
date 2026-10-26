"""Wiederkehrende Rechnungen: Termine, Abrechnungszeiträume und Platzhalter im Text."""

import calendar
import re
from datetime import date, timedelta

# Wert = Abstand in Monaten
INTERVALLE = {"monatlich": 1, "quartalsweise": 3, "halbjaehrlich": 6, "jaehrlich": 12}
INTERVALL_NAMEN = {
    "monatlich": "Jeden Monat",
    "quartalsweise": "Jedes Quartal",
    "halbjaehrlich": "Jedes halbe Jahr",
    "jaehrlich": "Jedes Jahr",
}
# Was passiert, wenn ein Termin da ist
VERSAND_ARTEN = {
    "entwurf": "Entwurf anlegen, ich prüfe und schicke ihn selbst",
    "festschreiben": "Rechnung automatisch festschreiben (Nummer und PDF), Versand von Hand",
    "senden": "Rechnung automatisch festschreiben und per E-Mail an den Kunden schicken",
}
MAX_NACHHOLEN = 12  # So viele verpasste Termine holt ein Lauf höchstens nach

MONATE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


class TerminFehler(ValueError):
    pass


def addiere_monate(start: date, monate: int, anker_tag: int) -> date:
    """Datum um Monate verschieben. Der Anker-Tag (z. B. 31) bleibt erhalten, kurze Monate
    nehmen ihren letzten Tag. So wird aus dem 31. Januar der 28. Februar und danach der 31. März."""
    index = start.year * 12 + (start.month - 1) + monate
    jahr, monat = divmod(index, 12)
    monat += 1
    tag = min(anker_tag, calendar.monthrange(jahr, monat)[1])
    return date(jahr, monat, tag)


def naechster_termin(termin: date, intervall: str, anker_tag: int) -> date:
    if intervall not in INTERVALLE:
        raise TerminFehler("Unbekanntes Intervall.")
    return addiere_monate(termin, INTERVALLE[intervall], anker_tag)


def zeitraum(start: date, intervall: str, anker_tag: int) -> tuple[date, date]:
    """Abrechnungszeitraum, der am Starttermin beginnt und am Tag vor dem nächsten endet."""
    return start, naechster_termin(start, intervall, anker_tag) - timedelta(days=1)


def faellige_termine(
    naechste_am: date, heute: date, intervall: str, anker_tag: int, ende_am: date | None = None
) -> list[date]:
    """Alle Termine bis heute (auch verpasste), höchstens MAX_NACHHOLEN, nicht nach dem Ende."""
    termine: list[date] = []
    termin = naechste_am
    while termin <= heute and len(termine) < MAX_NACHHOLEN:
        if ende_am is not None and termin > ende_am:
            break
        termine.append(termin)
        termin = naechster_termin(termin, intervall, anker_tag)
    return termine


def _quartal(datum: date) -> str:
    return f"Q{(datum.month - 1) // 3 + 1} {datum.year}"


def ersetze_platzhalter(text: str | None, von: date, bis: date) -> str | None:
    """{monat}, {jahr}, {quartal}, {zeitraum}, {von}, {bis} im Text durch Werte ersetzen."""
    if not text:
        return text
    werte = {
        "monat": f"{MONATE[von.month - 1]} {von.year}",
        "jahr": str(von.year),
        "quartal": _quartal(von),
        "zeitraum": f"{von:%d.%m.%Y} bis {bis:%d.%m.%Y}",
        "von": f"{von:%d.%m.%Y}",
        "bis": f"{bis:%d.%m.%Y}",
    }
    return re.sub(r"\{(monat|jahr|quartal|zeitraum|von|bis)\}", lambda m: werte[m.group(1)], text)
