"""Länder der EU. Für die Regel „Dienstleistung an ein Unternehmen im EU-Ausland“:
Ort der Leistung ist dann das Land des Kunden (§ 3a Abs. 2 UStG), der Kunde schuldet die
Steuer, und auf die Rechnung gehört „Steuerschuldnerschaft des Leistungsempfängers“
(§ 14a Abs. 1 UStG). Eine Zusammenfassende Meldung entfällt für Kleinunternehmer
(§ 18a Abs. 4 UStG)."""

import re

EU_LAENDER = {
    "BE": ("belgien", "belgium"),
    "BG": ("bulgarien", "bulgaria"),
    "DK": ("dänemark", "daenemark", "denmark"),
    "DE": ("deutschland", "germany"),
    "EE": ("estland", "estonia"),
    "FI": ("finnland", "finland"),
    "FR": ("frankreich", "france"),
    "GR": ("griechenland", "greece"),
    "IE": ("irland", "ireland"),
    "IT": ("italien", "italy"),
    "HR": ("kroatien", "croatia"),
    "LV": ("lettland", "latvia"),
    "LT": ("litauen", "lithuania"),
    "LU": ("luxemburg", "luxembourg"),
    "MT": ("malta",),
    "NL": ("niederlande", "holland", "netherlands"),
    "AT": ("österreich", "oesterreich", "austria"),
    "PL": ("polen", "poland"),
    "PT": ("portugal",),
    "RO": ("rumänien", "rumaenien", "romania"),
    "SE": ("schweden", "sweden"),
    "SK": ("slowakei", "slovakia"),
    "SI": ("slowenien", "slovenia"),
    "ES": ("spanien", "spain"),
    "CZ": ("tschechien", "czechia", "tschechische republik"),
    "HU": ("ungarn", "hungary"),
    "CY": ("zypern", "cyprus"),
}
# Griechenland nutzt in der USt-IdNr. „EL“
_KUERZEL = {"EL": "GR"}

REVERSE_CHARGE_TEXT = "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge)."


def eu_land(text: str | None) -> str | None:
    """ISO-Code eines EU-Landes aus Name oder Kürzel, sonst None. Leer heißt Deutschland."""
    wert = (text or "").strip()
    if not wert:
        return "DE"
    if re.fullmatch(r"[A-Za-z]{2}", wert):
        code = _KUERZEL.get(wert.upper(), wert.upper())
        return code if code in EU_LAENDER else None
    klein = wert.lower()
    for code, namen in EU_LAENDER.items():
        if klein in namen:
            return code
    return None


def ist_eu_ausland(text: str | None) -> bool:
    code = eu_land(text)
    return code is not None and code != "DE"
