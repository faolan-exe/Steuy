"""Umsatzgrenzen nach § 19 UStG. Die Werte liegen als Daten je Jahr vor, nicht im Code."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Grenze:
    gueltig_ab_jahr: int
    vorjahr_cent: int
    laufendes_jahr_cent: int


class KeineGrenzeHinterlegt(LookupError):
    pass


def grenze_fuer_jahr(grenzen: list[Grenze], jahr: int) -> Grenze:
    """Die jüngste Grenze, die im angegebenen Jahr schon galt."""
    passend = [g for g in grenzen if g.gueltig_ab_jahr <= jahr]
    if not passend:
        raise KeineGrenzeHinterlegt(f"Für {jahr} ist keine Kleinunternehmergrenze hinterlegt.")
    return max(passend, key=lambda g: g.gueltig_ab_jahr)
