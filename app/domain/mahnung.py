"""Wann ist welche Mahnstufe fällig? (docs/domain/mahnwesen.md)"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Stufe:
    nummer: int
    bezeichnung: str
    tage_nach: int  # Abstand zur Fälligkeit (Stufe 1) bzw. zur vorherigen Mahnung
    frist_tage: int  # neue Zahlungsfrist auf dem Schreiben


@dataclass(frozen=True)
class LetzteMahnung:
    stufe: int
    datum: date


def naechste_stufe(stufen: list[Stufe], letzte: LetzteMahnung | None) -> Stufe | None:
    sortiert = sorted(stufen, key=lambda s: s.nummer)
    if letzte is None:
        return sortiert[0] if sortiert else None
    spaeter = [s for s in sortiert if s.nummer > letzte.stufe]
    return spaeter[0] if spaeter else None


def faellige_stufe(
    *,
    faellig_am: date | None,
    letzte: LetzteMahnung | None,
    stufen: list[Stufe],
    heute: date,
) -> Stufe | None:
    if faellig_am is None:
        return None
    stufe = naechste_stufe(stufen, letzte)
    if stufe is None:
        return None
    basis = faellig_am if letzte is None else letzte.datum
    return stufe if heute >= basis + timedelta(days=stufe.tage_nach) else None


def faellig_ab(
    *, faellig_am: date | None, letzte: LetzteMahnung | None, stufe: Stufe
) -> date | None:
    """Ab wann die Stufe laut Zeitplan dran ist. Früher erstellen darf man sie, aber der Kunde
    bekommt dann weniger Zeit als vorgesehen."""
    if faellig_am is None:
        return None
    basis = faellig_am if letzte is None else letzte.datum
    return basis + timedelta(days=stufe.tage_nach)
