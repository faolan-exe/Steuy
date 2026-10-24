"""Zahlungen am Jahreswechsel erkennen und ihre Zuordnung bestätigen (docs/domain/euer.md)."""

from datetime import date, timedelta

from sqlalchemy import func, select

from app.domain.jahreswechsel import MINDEST_VORGAENGER, anderes_jahr, im_fenster
from app.extensions import db
from app.models import Anlagegut, Buchung, Jahreszuordnung, Zahlung
from app.services.protokoll import protokolliere


class ZuordnungUngueltig(ValueError):
    pass


def _regelmaessig(buchung: Buchung, datum: date) -> bool:
    """Mindestens zwei frühere Buchungen gleicher Art beim selben Kontakt bzw. Partner
    im Jahr davor. Großzügig, weil jeder Fall ohnehin bestätigt wird."""
    abfrage = select(func.count(Buchung.id)).where(
        Buchung.id != buchung.id,
        Buchung.art == buchung.art,
        Buchung.status == "festgeschrieben",
        Buchung.storno_von_id.is_(None),
        Buchung.belegdatum >= datum - timedelta(days=400),
        Buchung.belegdatum < datum,
    )
    if buchung.kontakt_id:
        abfrage = abfrage.where(Buchung.kontakt_id == buchung.kontakt_id)
    elif buchung.partner:
        abfrage = abfrage.where(func.lower(Buchung.partner) == buchung.partner.lower())
    else:
        return False
    return db.session.execute(abfrage).scalar() >= MINDEST_VORGAENGER


def kandidaten(heute: date | None = None) -> list[Zahlung]:
    """Unentschiedene Zahlungen der letzten zwei Jahreswechsel."""
    heute = heute or date.today()
    entschieden = select(Jahreszuordnung.zahlung_id)
    storniert = select(Zahlung.storno_von_id).where(Zahlung.storno_von_id.is_not(None))
    anlagen = select(Anlagegut.buchung_id)
    zahlungen = db.session.execute(
        select(Zahlung)
        .join(Buchung, Zahlung.buchung_id == Buchung.id)
        .where(
            Zahlung.storno_von_id.is_(None),
            Zahlung.id.not_in(entschieden),
            Zahlung.id.not_in(storniert),
            Buchung.id.not_in(anlagen),
            Zahlung.datum >= heute - timedelta(days=800),
        )
        .order_by(Zahlung.datum)
    ).scalars()
    return [z for z in zahlungen if im_fenster(z.datum) and _regelmaessig(z.buchung, z.datum)]


def bestaetige(zahlung: Zahlung, jahr: int, nutzer_id: int) -> Jahreszuordnung:
    if jahr not in (zahlung.datum.year, anderes_jahr(zahlung.datum)):
        raise ZuordnungUngueltig("Nur das Zahlungsjahr oder das Nachbarjahr ist möglich.")
    if not im_fenster(zahlung.datum):
        raise ZuordnungUngueltig("Die Zahlung liegt nicht am Jahreswechsel.")
    if db.session.get(Jahreszuordnung, zahlung.id):
        raise ZuordnungUngueltig("Für diese Zahlung ist das Jahr schon festgelegt.")
    eintrag = Jahreszuordnung(zahlung_id=zahlung.id, jahr=jahr, bestaetigt_von=nutzer_id)
    db.session.add(eintrag)
    protokolliere(
        "jahreszuordnung",
        nutzer_id=nutzer_id,
        objekt_typ="buchung",
        objekt_id=zahlung.buchung_id,
        details={"zahlung_id": zahlung.id, "jahr": jahr, "datum": zahlung.datum.isoformat()},
    )
    db.session.commit()
    return eintrag


def zuordnungen() -> dict[int, int]:
    """Zahlung → EÜR-Jahr für alle bestätigten Fälle."""
    return dict(db.session.execute(select(Jahreszuordnung.zahlung_id, Jahreszuordnung.jahr)).all())
