from datetime import date

from flask import Flask

from app.domain.geld import cent_zu_euro
from app.domain.rechnung import menge_als_text
from app.domain.zahlung import ZAHLUNGSARTEN


def datum(wert: date | None) -> str:
    return wert.strftime("%d.%m.%Y") if wert else ""


def prozent(basispunkte: int) -> str:
    """1250 → „12,5“."""
    ganz, rest = divmod(basispunkte, 100)
    return str(ganz) if not rest else f"{ganz},{rest:02d}".rstrip("0")


def registriere_filter(app: Flask) -> None:
    app.add_template_filter(cent_zu_euro, "euro")
    app.add_template_filter(datum, "datum")
    app.add_template_filter(menge_als_text, "menge")
    app.add_template_filter(prozent, "prozent")
    app.add_template_filter(lambda art: ZAHLUNGSARTEN.get(art, art), "zahlungsart")
