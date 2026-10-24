"""Regelmäßig wiederkehrende Zahlungen um den Jahreswechsel (§ 11 EStG, docs/domain/euer.md).

steuy schlägt nur vor. Ob die Zahlung zum anderen Jahr gehört, bestätigt der Nutzer.
"""

from datetime import date

FENSTER_TAGE = 10
MINDEST_VORGAENGER = 2


def im_fenster(datum: date) -> bool:
    """22.12. bis 10.01. (je 10 Tage vor und nach dem 31.12.)."""
    return (datum.month == 12 and datum.day >= 22) or (datum.month == 1 and datum.day <= 10)


def anderes_jahr(datum: date) -> int:
    """Das Jahr, zu dem die Zahlung wirtschaftlich gehören könnte."""
    return datum.year + 1 if datum.month == 12 else datum.year - 1


def frage(datum: date) -> str:
    jahr = anderes_jahr(datum)
    return f"Gehört diese Zahlung vom {datum:%d.%m.%Y} wirtschaftlich zu {jahr}?"
