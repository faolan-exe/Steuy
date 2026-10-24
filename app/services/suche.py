"""Globale Suche über Kontakte, Rechnungen, Buchungen, Belege und Artikel."""

from sqlalchemy import or_, select

from app.domain.geld import GeldFormatFehler, euro_zu_cent
from app.extensions import db
from app.models import Beleg, Buchung, Rechnung
from app.services.artikel import suche_artikel
from app.services.kontakte import suche_kontakte

MIN_ZEICHEN = 2
LIMIT = 10


def _betrag(text: str) -> int | None:
    """„807,60“ oder „807.60 €“ findet auch Beträge. Reine Ganzzahlen wie „2026“ nicht,
    sonst käme zu jeder Jahreszahl eine Zufallsmenge Treffer."""
    if not any(z in text for z in ",."):
        return None
    try:
        return euro_zu_cent(text)
    except (GeldFormatFehler, ValueError):
        return None


def suche(text: str, limit: int = LIMIT) -> dict[str, list]:
    text = (text or "").strip()
    leer = {"kontakte": [], "rechnungen": [], "buchungen": [], "belege": [], "artikel": []}
    if len(text) < MIN_ZEICHEN:
        return leer
    muster = f"%{text}%"
    cent = _betrag(text)

    bedingung = [
        Rechnung.nummer.ilike(muster),
        Rechnung.empfaenger_name.ilike(muster),
        Rechnung.titel.ilike(muster),
    ]
    if cent is not None:
        bedingung.append(Rechnung.summe_cent == cent)
    rechnungen = db.session.execute(
        select(Rechnung)
        .where(or_(*bedingung), Rechnung.nummer.is_not(None) | (Rechnung.status == "entwurf"))
        .order_by(Rechnung.rechnungsdatum.desc(), Rechnung.id.desc())
        .limit(limit)
    ).scalars()

    bedingung = [
        Buchung.partner.ilike(muster),
        Buchung.belegnummer.ilike(muster),
        Buchung.beschreibung.ilike(muster),
    ]
    if cent is not None:
        bedingung.append(Buchung.betrag_cent == cent)
    buchungen = db.session.execute(
        select(Buchung)
        .where(or_(*bedingung))
        .order_by(Buchung.belegdatum.desc(), Buchung.id.desc())
        .limit(limit)
    ).scalars()

    belege = db.session.execute(
        select(Beleg)
        .where(Beleg.dateiname.ilike(muster), Beleg.verworfen.is_(False))
        .order_by(Beleg.id.desc())
        .limit(limit)
    ).scalars()

    return {
        "kontakte": suche_kontakte(text)[:limit],
        "rechnungen": list(rechnungen),
        "buchungen": list(buchungen),
        "belege": list(belege),
        "artikel": suche_artikel(text)[:limit],
    }
