"""Suche ohne Rücksicht auf Umlaute: „koln“, „koeln“ und „Köln“ finden dasselbe.

Spalte und Suchtext werden gleich vereinfacht: klein, ä/ö/ü zu a/o/u, ae/oe/ue zu a/o/u,
ß zu ss, Akzente weg."""

from sqlalchemy import func

_ZEICHEN = "äöüéèêáàâíìîóòôúùûç"
_ERSATZ = "aoueeeaaaiiiooouuuc"
_PAARE = (("ae", "a"), ("oe", "o"), ("ue", "u"), ("ß", "ss"))


def norm(text: str) -> str:
    t = text.casefold().translate(str.maketrans(_ZEICHEN, _ERSATZ))
    for alt, neu in _PAARE:
        t = t.replace(alt, neu)
    return t


def normiert(spalte):
    """Dieselbe Vereinfachung in SQL."""
    ausdruck = func.translate(func.lower(spalte), _ZEICHEN, _ERSATZ)
    for alt, neu in _PAARE:
        ausdruck = func.replace(ausdruck, alt, neu)
    return ausdruck


def enthaelt(spalte, text: str):
    """Bedingung: Spalte enthält den Text (ohne Umlaut-Unterschiede)."""
    muster = norm(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return normiert(spalte).like(f"%{muster}%")
