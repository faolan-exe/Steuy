"""Abschreibung (AfA) von Anschaffungen, Version 1 (docs/domain/euer.md).

Alles in ganzen Cent: Die Jahresbeträge ergeben zusammen exakt die Anschaffungskosten.
"""

from datetime import date

# Art → Kennzahl der Anlage EÜR (stabiler als die Zeilennummer, die sich jährlich ändert)
ARTEN = {
    "computer": ("Computerhardware", "130"),
    "software": ("Software", "131"),
    "beweglich": ("Anderes bewegliches Wirtschaftsgut (z. B. Möbel, Kamera, Fahrzeug)", "130"),
    "immateriell": ("Anderes immaterielles Wirtschaftsgut (z. B. Lizenz, Website)", "131"),
}
# Nutzungsdauer 1 Jahr, volle AfA im Anschaffungsjahr (BMF-Schreiben vom 22.02.2022)
SOFORT = {"computer", "software"}


class AfaUngueltig(ValueError):
    pass


def gwg_grenze_brutto(grenze_netto_cent: int, steuersatz_prozent: int) -> int:
    """Die GWG-Grenze gilt netto. Kleinunternehmer zahlen brutto, daher umrechnen."""
    return grenze_netto_cent * (100 + steuersatz_prozent) // 100


def ist_gwg(betrag_brutto_cent: int, grenze_netto_cent: int, steuersatz_prozent: int) -> bool:
    return betrag_brutto_cent <= gwg_grenze_brutto(grenze_netto_cent, steuersatz_prozent)


def plan(
    anschaffungskosten_cent: int, anschaffung: date, nutzungsdauer_jahre: int, art: str
) -> dict[int, int]:
    """Jahr → AfA-Betrag. Linear, im Anschaffungsjahr zeitanteilig nach vollen Monaten
    (der Anschaffungsmonat zählt mit)."""
    if art not in ARTEN:
        raise AfaUngueltig(f"Unbekannte Art: {art}")
    if anschaffungskosten_cent <= 0:
        raise AfaUngueltig("Die Anschaffungskosten müssen größer als 0 sein.")
    if art in SOFORT:
        return {anschaffung.year: anschaffungskosten_cent}
    if not nutzungsdauer_jahre or not 1 <= nutzungsdauer_jahre <= 50:
        raise AfaUngueltig("Die Nutzungsdauer muss zwischen 1 und 50 Jahren liegen.")
    monate_gesamt = nutzungsdauer_jahre * 12
    ergebnis: dict[int, int] = {}
    bisher = 0
    monat = anschaffung.month - 1  # 0-basiert
    jahr = anschaffung.year
    gezaehlt = 0
    while gezaehlt < monate_gesamt:
        monate_im_jahr = min(12 - monat, monate_gesamt - gezaehlt)
        gezaehlt += monate_im_jahr
        bis_ende = anschaffungskosten_cent * gezaehlt // monate_gesamt
        ergebnis[jahr] = bis_ende - bisher
        bisher = bis_ende
        jahr += 1
        monat = 0
    return ergebnis


def restbuchwert(anschaffungskosten_cent: int, afa_plan: dict[int, int], jahresende: int) -> int:
    return anschaffungskosten_cent - sum(b for j, b in afa_plan.items() if j <= jahresende)
