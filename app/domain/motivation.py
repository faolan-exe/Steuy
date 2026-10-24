"""Kleine Ermutigung auf dem Dashboard: ein Spruch passend zum Stand und das nächste Ziel."""

from datetime import date

MEILENSTEINE = (1, 5, 10, 25, 50, 100, 250, 500, 1000)


def naechster_meilenstein(anzahl: int) -> int:
    return next((m for m in MEILENSTEINE if m > anzahl), anzahl + 100)


def _euro(cent: int) -> str:
    vorzeichen = "-" if cent < 0 else ""
    euro = f"{abs(cent) // 100:,}".replace(",", ".")
    return f"{vorzeichen}{euro} €"


def spruch(
    *,
    gesamt: int,
    bezahlt: int,
    offen: int,
    ueberfaellig: int,
    einnahmen_cent: int,
    jahr: int,
    heute: date,
) -> dict:
    """Wählt aus passenden Sprüchen einen aus, der sich täglich ändert.

    `gesamt` ist die Zahl aller geschriebenen Rechnungen (über alle Jahre), die übrigen Zahlen
    beziehen sich auf das angezeigte Jahr."""
    ziel = naechster_meilenstein(gesamt)
    vorheriges = max((m for m in MEILENSTEINE if m <= gesamt), default=0)
    fortschritt = round(100 * (gesamt - vorheriges) / (ziel - vorheriges)) if gesamt else 0
    if gesamt == 0:
        texte = [
            "Die erste Rechnung ist der schwerste Schritt. Du schaffst das!",
            "Los geht's: Schreib deine erste Rechnung.",
        ]
    else:
        texte = [
            f"Du hast schon {gesamt} Rechnung{'en' if gesamt != 1 else ''} geschrieben. Super!",
            f"{gesamt} Rechnung{'en' if gesamt != 1 else ''} geschrieben: Dein Geschäft läuft.",
        ]
        if einnahmen_cent > 0:
            texte.append(f"Schon {_euro(einnahmen_cent)} Einnahmen in {jahr}. Weiter so!")
        if bezahlt and not offen and not ueberfaellig:
            texte.append("Alle Rechnungen bezahlt. Stark!")
        elif bezahlt:
            texte.append(
                f"{bezahlt} Rechnung{'en' if bezahlt != 1 else ''} schon bezahlt. Gut gemacht!"
            )
        if ueberfaellig:
            texte.append(
                f"{ueberfaellig} überfällig: Eine freundliche Erinnerung wirkt oft Wunder."
            )
    return {
        "text": texte[heute.toordinal() % len(texte)],
        "ziel": ziel,
        "fortschritt": fortschritt,
        "noch": ziel - gesamt,
    }


ZIELARTEN = {
    "auftraege": "Abgeschlossene Aufträge (bezahlte Rechnungen)",
    "umsatz": "Umsatz (Zahlungseingänge)",
    "gewinn": "Gewinn (Einnahmen minus Ausgaben)",
}


def ziel_stand(art: str, ziel: int, aktuell: int) -> dict:
    """Fortschritt zu einem selbst gewählten Ziel. Ein negativer Gewinn zählt als 0 Prozent."""
    erreicht = ziel > 0 and aktuell >= ziel
    fortschritt = 100 if erreicht else max(0, min(99, (100 * aktuell) // ziel)) if ziel > 0 else 0
    if art == "auftraege":
        noch = f"Noch {max(0, ziel - aktuell)} bis zu {ziel} abgeschlossenen Aufträgen"
        text_erreicht = f"Ziel erreicht: {aktuell} abgeschlossene Aufträge. Glückwunsch!"
    else:
        name = "Umsatz" if art == "umsatz" else "Gewinn"
        noch = f"Noch {_euro(max(0, ziel - aktuell))} bis {_euro(ziel)} {name}"
        text_erreicht = f"Ziel erreicht: {_euro(aktuell)} {name}. Glückwunsch!"
    return {
        "art": art,
        "erreicht": erreicht,
        "fortschritt": fortschritt,
        "noch_text": noch,
        "erreicht_text": text_erreicht,
    }
