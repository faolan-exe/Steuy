"""Regeln für Einnahmen und Ausgaben (docs/domain/euer.md)."""


def betrieblicher_anteil(betrag_cent: int, prozent: int) -> int:
    """Betrieblicher Teil eines Betrags, kaufmännisch auf Cent gerundet."""
    if not 0 <= prozent <= 100:
        raise ValueError("Der betriebliche Anteil liegt zwischen 0 und 100 %.")
    zaehler = betrag_cent * prozent
    vorzeichen = -1 if zaehler < 0 else 1
    ganz, rest = divmod(abs(zaehler), 100)
    if 2 * rest >= 100:
        ganz += 1
    return vorzeichen * ganz
