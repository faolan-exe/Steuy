"""Einnahmen-Überschuss-Rechnung: Posten auf Zeilen der Anlage EÜR verteilen.

Zeilen und Zuordnungen kommen je Steuerjahr aus der Datenbank (docs/domain/euer.md).
"""

from dataclasses import dataclass, field
from datetime import date

# Pseudo-Zeilen für Kategorien ohne Zuordnung im gewählten Jahr
OHNE_ZUORDNUNG = {"einnahme": -1, "ausgabe": 0}


@dataclass(frozen=True)
class Zeile:
    nummer: int
    kennzahl: str | None
    bezeichnung: str
    art: str  # "einnahme" oder "ausgabe"


@dataclass(frozen=True)
class Posten:
    zeile: int
    art: str
    datum: date
    text: str
    betrag_cent: int


@dataclass(frozen=True)
class Summenzeilen:
    """Wo die Summen im Vordruck stehen (ändert sich von Jahr zu Jahr)."""

    einnahmen_zeile: int
    einnahmen_kz: str
    ausgaben_zeile: int
    ausgaben_kz: str
    gewinn_einnahmen_zeile: int
    gewinn_ausgaben_zeile: int


@dataclass
class Ergebnis:
    jahr: int
    vordruck_jahr: int | None
    summen: Summenzeilen | None = None
    einnahmen: list[tuple[Zeile, int, list[Posten]]] = field(default_factory=list)
    ausgaben: list[tuple[Zeile, int, list[Posten]]] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    @property
    def summe_einnahmen(self) -> int:
        return sum(betrag for _, betrag, _ in self.einnahmen)

    @property
    def summe_ausgaben(self) -> int:
        return sum(betrag for _, betrag, _ in self.ausgaben)

    @property
    def gewinn(self) -> int:
        return self.summe_einnahmen - self.summe_ausgaben


def verteile(
    jahr: int,
    vordruck_jahr: int | None,
    zeilen: list[Zeile],
    posten: list[Posten],
    summen: Summenzeilen | None = None,
):
    nach_nummer = {z.nummer: z for z in zeilen}
    ergebnis = Ergebnis(jahr=jahr, vordruck_jahr=vordruck_jahr, summen=summen)
    gruppen: dict[int, list[Posten]] = {}
    for p in posten:
        gruppen.setdefault(p.zeile, []).append(p)

    for nummer in sorted(gruppen, key=lambda n: (n <= 0, n)):
        liste = sorted(gruppen[nummer], key=lambda p: (p.datum, p.text))
        betrag = sum(p.betrag_cent for p in liste)
        if nummer in OHNE_ZUORDNUNG.values():
            zeile = Zeile(nummer, None, "Ohne Zuordnung zur Anlage EÜR", liste[0].art)
            hinweis = (
                "Einige Kategorien haben für dieses Jahr keine Zeile der Anlage EÜR. "
                "Sie sind in den Summen enthalten, aber keiner Zeile zugeordnet."
            )
            if hinweis not in ergebnis.hinweise:
                ergebnis.hinweise.append(hinweis)
        else:
            zeile = nach_nummer[nummer]
        ziel = ergebnis.einnahmen if zeile.art == "einnahme" else ergebnis.ausgaben
        ziel.append((zeile, betrag, liste))

    if vordruck_jahr is None:
        ergebnis.hinweise.append("Für dieses Jahr ist keine Zuordnung zur Anlage EÜR hinterlegt.")
    elif vordruck_jahr != jahr:
        ergebnis.hinweise.append(
            f"Die Zeilennummern stammen aus dem Vordruck {vordruck_jahr}. Für {jahr} sind sie "
            "noch nicht geprüft. Bitte vor dem Übertragen mit dem aktuellen Vordruck vergleichen."
        )
    return ergebnis
