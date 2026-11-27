"""Globale Suche über Kontakte, Rechnungen, Buchungen, Belege und Artikel."""

import re

from sqlalchemy import Integer, and_, func, or_, select

from app.domain.geld import GeldFormatFehler, euro_zu_cent
from app.extensions import db
from app.models import Beleg, Buchung, Rechnung, Rechnungsposition
from app.services.artikel import suche_artikel
from app.services.kontakte import suche_kontakte
from app.services.suchnorm import enthaelt, norm

MIN_ZEICHEN = 2
LIMIT = 10


def _betrag(text: str) -> int | None:
    """„807,60“, „807.60 €“ oder „1200“ findet auch Beträge. Jahreszahlen wie „2026“ nicht,
    sonst käme zu jeder Jahreszahl eine Zufallsmenge Treffer."""
    ganzzahl = not any(z in text for z in ",.")
    jahreszahl = text.isdigit() and len(text) == 4 and 1990 <= int(text) <= 2100
    if ganzzahl and (not text.isdigit() or len(text) > 7 or jahreszahl):
        return None
    try:
        return euro_zu_cent(text)
    except (GeldFormatFehler, ValueError):
        return None


def _betragsbereich(text: str) -> tuple[int, int] | None:
    """Ganze Euro („1250“) finden auch 1.250,50 €: Wer sucht, kennt die Cent oft nicht."""
    cent = _betrag(text)
    if cent is None:
        return None
    ganze_euro = not any(z in text for z in ",.")
    return (cent, cent + 99) if ganze_euro else (cent, cent)


def _kontakte(text: str) -> list:
    woerter = norm(text).split()
    if len(woerter) < 2:
        return suche_kontakte(text)
    treffer = suche_kontakte(max(woerter, key=len))
    return [
        k
        for k in treffer
        if all(w in norm(" ".join(filter(None, [k.name, k.ort, k.email]))) for w in woerter)
    ]


def suche(text: str, limit: int = LIMIT) -> dict[str, list]:
    text = (text or "").strip()
    leer = {"kontakte": [], "rechnungen": [], "buchungen": [], "belege": [], "artikel": []}
    if len(text) < MIN_ZEICHEN:
        return leer
    muster = f"%{text}%"
    bereich = _betragsbereich(text)

    def passt(wort: str):
        positionen = select(Rechnungsposition.rechnung_id).where(
            or_(
                enthaelt(Rechnungsposition.bezeichnung, wort),
                enthaelt(Rechnungsposition.beschreibung, wort),
            )
        )
        return or_(
            Rechnung.nummer.ilike(f"%{wort}%"),
            enthaelt(Rechnung.empfaenger_name, wort),
            enthaelt(Rechnung.titel, wort),
            Rechnung.id.in_(positionen),
        )

    # Mehrere Wörter: jedes muss irgendwo vorkommen („mustermann max“, „hochzeit schmitz“)
    bedingung = [and_(*[passt(w) for w in text.split()])]
    if bereich is not None:
        bedingung.append(Rechnung.summe_cent.between(*bereich))
    kurz = re.fullmatch(r"([A-Za-z]+)[\s/-]*0*(\d{1,6})", text)
    if kurz:
        # „RE5“ findet „RE0005“
        ziffern = func.nullif(func.regexp_replace(Rechnung.nummer, "[^0-9]", "", "g"), "")
        bedingung.append(
            and_(Rechnung.nummer.ilike(f"{kurz[1]}%"), ziffern.cast(Integer) == int(kurz[2]))
        )
    rechnungen = db.session.execute(
        select(Rechnung)
        .where(or_(*bedingung), Rechnung.nummer.is_not(None) | (Rechnung.status == "entwurf"))
        .order_by(Rechnung.rechnungsdatum.desc(), Rechnung.id.desc())
        .limit(limit)
    ).scalars()

    bedingung = [
        enthaelt(Buchung.partner, text),
        Buchung.belegnummer.ilike(muster),
        enthaelt(Buchung.beschreibung, text),
    ]
    if bereich is not None:
        bedingung.append(Buchung.betrag_cent.between(*bereich))
    buchungen = db.session.execute(
        select(Buchung)
        .where(or_(*bedingung))
        .order_by(Buchung.belegdatum.desc(), Buchung.id.desc())
        .limit(limit)
    ).scalars()

    belege = db.session.execute(
        select(Beleg)
        .where(enthaelt(Beleg.dateiname, text), Beleg.verworfen.is_(False))
        .order_by(Beleg.id.desc())
        .limit(limit)
    ).scalars()

    return {
        "kontakte": _kontakte(text)[:limit],
        "rechnungen": list(rechnungen),
        "buchungen": list(buchungen),
        "belege": list(belege),
        "artikel": suche_artikel(text)[:limit],
    }
