"""Einnahmen und Ausgaben: Entwurf, Festschreiben, Zahlung, Storno (ADR 0002)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.domain.zahlung import ZahlungUngueltig, offene_gebuehr, pruefe_zahlung
from app.extensions import db
from app.models import Buchung, BuchungGebuehr, Kategorie, Zahlung
from app.services.protokoll import protokolliere


class BuchungUngueltig(ValueError):
    pass


@dataclass
class Buchungsdaten:
    art: str
    belegdatum: date
    betrag_cent: int
    kategorie_id: int | None
    betrieblich_prozent: int = 100
    kontakt_id: int | None = None
    partner: str | None = None
    belegnummer: str | None = None
    beschreibung: str | None = None
    beleg_id: int | None = None


def kategorien(art: str | None = None) -> list[Kategorie]:
    abfrage = select(Kategorie).where(Kategorie.aktiv).order_by(Kategorie.sortierung)
    if art:
        abfrage = abfrage.where(Kategorie.art == art)
    return list(db.session.execute(abfrage).scalars())


def _pruefe(daten: Buchungsdaten) -> None:
    if daten.art not in ("einnahme", "ausgabe"):
        raise BuchungUngueltig("Bitte Einnahme oder Ausgabe wählen.")
    if daten.betrag_cent <= 0:
        raise BuchungUngueltig("Der Betrag muss größer als 0 sein.")
    if not 0 <= daten.betrieblich_prozent <= 100:
        raise BuchungUngueltig("Der betriebliche Anteil liegt zwischen 0 und 100 %.")
    if daten.kategorie_id is not None:
        kategorie = db.session.get(Kategorie, daten.kategorie_id)
        if kategorie is None or kategorie.art != daten.art:
            raise BuchungUngueltig("Die Kategorie passt nicht zur Art der Buchung.")


def lege_entwurf_an(daten: Buchungsdaten, nutzer_id: int) -> Buchung:
    _pruefe(daten)
    if daten.beleg_id is not None:
        bisherige = db.session.execute(
            select(Buchung).where(
                Buchung.beleg_id == daten.beleg_id, Buchung.storno_von_id.is_(None)
            )
        ).scalars()
        if any(not b.storniert for b in bisherige):
            raise BuchungUngueltig(
                "Zu diesem Beleg gibt es schon eine Buchung. Bitte erst stornieren, "
                "falls etwas falsch war."
            )
    buchung = Buchung(**vars(daten), status="entwurf", erstellt_von=nutzer_id)
    db.session.add(buchung)
    db.session.flush()
    protokolliere(
        "buchung_entwurf", nutzer_id=nutzer_id, objekt_typ="buchung", objekt_id=buchung.id
    )
    db.session.commit()
    return buchung


def aendere_entwurf(buchung: Buchung, daten: Buchungsdaten) -> None:
    if not buchung.ist_entwurf:
        raise BuchungUngueltig("Festgeschriebene Buchungen können nicht geändert werden.")
    _pruefe(daten)
    for feld, wert in vars(daten).items():
        setattr(buchung, feld, wert)
    db.session.commit()


def loesche_entwurf(buchung: Buchung, nutzer_id: int) -> None:
    if not buchung.ist_entwurf:
        raise BuchungUngueltig("Festgeschriebene Buchungen können nur storniert werden.")
    protokolliere(
        "buchung_entwurf_geloescht", nutzer_id=nutzer_id, objekt_typ="buchung", objekt_id=buchung.id
    )
    db.session.delete(buchung)
    db.session.commit()


def _neue_zahlung(
    buchung: Buchung, datum: date, betrag_cent: int, zahlungsart: str, nutzer_id: int, **mehr
):
    zahlung = Zahlung(
        buchung_id=buchung.id,
        datum=datum,
        betrag_cent=betrag_cent,
        zahlungsart=zahlungsart,
        erfasst_von=nutzer_id,
        **mehr,
    )
    db.session.add(zahlung)
    db.session.flush()
    return zahlung


def pruefe_festschreibbar(daten: Buchungsdaten, bezahlt_am: date | None) -> None:
    """Prüft vorab, damit bei einem Fehler kein halber Entwurf entsteht."""
    _pruefe(daten)
    if daten.kategorie_id is None:
        raise BuchungUngueltig("Bitte vor dem Festschreiben eine Kategorie wählen.")
    if bezahlt_am:
        pruefe_zahlung(
            betrag_cent=daten.betrag_cent,
            offen_cent=daten.betrag_cent,
            angekommen_cent=None,
            datum=bezahlt_am,
            rechnungsdatum=daten.belegdatum,
        )


def festschreiben(
    buchung: Buchung,
    nutzer_id: int,
    bezahlt_am: date | None = None,
    zahlungsart: str | None = None,
) -> Buchung:
    """Schreibt fest. Optional gleich mit Zahlung, wenn schon bezahlt."""
    if not buchung.ist_entwurf:
        raise BuchungUngueltig("Die Buchung ist bereits festgeschrieben.")
    if buchung.kategorie_id is None:
        raise BuchungUngueltig("Bitte vor dem Festschreiben eine Kategorie wählen.")
    if bezahlt_am:
        pruefe_zahlung(
            betrag_cent=buchung.betrag_cent,
            offen_cent=buchung.betrag_cent,
            angekommen_cent=None,
            datum=bezahlt_am,
            rechnungsdatum=buchung.belegdatum,
        )
    buchung.status = "festgeschrieben"
    buchung.festgeschrieben_am = datetime.now(UTC)
    buchung.festgeschrieben_von = nutzer_id
    db.session.flush()
    if bezahlt_am:
        _neue_zahlung(
            buchung, bezahlt_am, buchung.betrag_cent, zahlungsart or "ueberweisung", nutzer_id
        )
    protokolliere(
        "buchung_festgeschrieben",
        nutzer_id=nutzer_id,
        objekt_typ="buchung",
        objekt_id=buchung.id,
        details={"art": buchung.art, "betrag_cent": buchung.betrag_cent},
    )
    db.session.commit()
    db.session.refresh(buchung, ["zahlungen"])
    return buchung


def erfasse_zahlung(
    buchung: Buchung,
    *,
    datum: date,
    betrag_cent: int,
    zahlungsart: str,
    notiz: str | None,
    nutzer_id: int,
) -> Zahlung:
    if buchung.ist_entwurf or buchung.zahlstatus == "storniert":
        raise ZahlungUngueltig(
            "Zahlungen gibt es nur zu festgeschriebenen, nicht stornierten Buchungen."
        )
    pruefe_zahlung(
        betrag_cent=betrag_cent,
        offen_cent=buchung.offen_cent,
        angekommen_cent=None,
        datum=datum,
        rechnungsdatum=buchung.belegdatum,
    )
    zahlung = _neue_zahlung(
        buchung, datum, betrag_cent, zahlungsart, nutzer_id, notiz=(notiz or "").strip() or None
    )
    protokolliere(
        "zahlung_erfasst",
        nutzer_id=nutzer_id,
        objekt_typ="buchung",
        objekt_id=buchung.id,
        details={"zahlung_id": zahlung.id, "datum": datum.isoformat(), "betrag_cent": betrag_cent},
    )
    db.session.commit()
    db.session.refresh(buchung, ["zahlungen"])
    return zahlung


def storniere(buchung: Buchung, nutzer_id: int) -> Buchung:
    """Gegenbuchung mit negativem Betrag, Zahlungen werden ebenfalls gegengebucht."""
    if buchung.ist_entwurf:
        raise BuchungUngueltig("Entwürfe werden gelöscht, nicht storniert.")
    if buchung.storno_von_id is not None or buchung.storniert:
        raise BuchungUngueltig("Diese Buchung ist bereits storniert.")
    jetzt = datetime.now(UTC)
    storno = Buchung(
        art=buchung.art,
        status="festgeschrieben",
        beleg_id=buchung.beleg_id,
        kontakt_id=buchung.kontakt_id,
        partner=buchung.partner,
        belegdatum=buchung.belegdatum,
        belegnummer=buchung.belegnummer,
        beschreibung="Storno",
        kategorie_id=buchung.kategorie_id,
        betrag_cent=-buchung.betrag_cent,
        betrieblich_prozent=buchung.betrieblich_prozent,
        storno_von_id=buchung.id,
        festgeschrieben_am=jetzt,
        festgeschrieben_von=nutzer_id,
        erstellt_von=nutzer_id,
    )
    db.session.add(storno)
    db.session.flush()
    for zahlung in [z for z in buchung.zahlungen if z.storno_von_id is None]:
        if any(g.storno_von_id == zahlung.id for g in buchung.zahlungen):
            continue
        _neue_zahlung(
            buchung,
            zahlung.datum,
            -zahlung.betrag_cent,
            zahlung.zahlungsart,
            nutzer_id,
            notiz="Storno der Buchung",
            storno_von_id=zahlung.id,
        )
    protokolliere(
        "buchung_storniert",
        nutzer_id=nutzer_id,
        objekt_typ="buchung",
        objekt_id=buchung.id,
        details={"storno_id": storno.id, "betrag_cent": buchung.betrag_cent},
    )
    db.session.commit()
    db.session.refresh(buchung, ["zahlungen", "storno"])
    return storno


def offene_gebuehren() -> list[Zahlung]:
    storno = aliased(Buchung)
    erfasst = (
        select(BuchungGebuehr.zahlung_id)
        .join(Buchung, Buchung.id == BuchungGebuehr.buchung_id)
        .where(~select(storno.id).where(storno.storno_von_id == Buchung.id).exists())
    )
    kandidaten = db.session.execute(
        select(Zahlung)
        .where(
            Zahlung.angekommen_cent.is_not(None),
            Zahlung.storno_von_id.is_(None),
            Zahlung.id.not_in(erfasst),
        )
        .order_by(Zahlung.datum)
    ).scalars()
    ergebnis = []
    for zahlung in kandidaten:
        gegen = db.session.execute(
            select(Zahlung.id).where(Zahlung.storno_von_id == zahlung.id)
        ).first()
        if not gegen and offene_gebuehr(zahlung.betrag_cent, zahlung.angekommen_cent) > 0:
            ergebnis.append(zahlung)
    return ergebnis


def erfasse_gebuehren(zahlung_ids: list[int], nutzer_id: int) -> Buchung:
    """Eine Ausgabe „Gebühren“ für die gewählten Zahlungen. Abfluss je Gebühr am Zahlungstag."""
    offen = {z.id: z for z in offene_gebuehren()}
    gewaehlt = [offen[i] for i in zahlung_ids if i in offen]
    if not gewaehlt:
        raise BuchungUngueltig("Bitte mindestens eine offene Gebühr auswählen.")
    kategorie = db.session.execute(
        select(Kategorie).where(Kategorie.name == "Gebühren", Kategorie.art == "ausgabe")
    ).scalar_one_or_none()
    gebuehren = [(z, offene_gebuehr(z.betrag_cent, z.angekommen_cent)) for z in gewaehlt]
    arten = sorted({z.zahlungsart for z in gewaehlt})
    buchung = Buchung(
        art="ausgabe",
        status="festgeschrieben",
        partner=", ".join({"paypal": "PayPal", "karte": "Kartenzahlung"}.get(a, a) for a in arten),
        belegdatum=max(z.datum for z in gewaehlt),
        beschreibung="Zahlungsgebühren zu "
        + ", ".join(z.rechnung.nummer if z.rechnung else f"Zahlung {z.id}" for z in gewaehlt),
        kategorie_id=kategorie.id if kategorie else None,
        betrag_cent=sum(g for _, g in gebuehren),
        festgeschrieben_am=datetime.now(UTC),
        festgeschrieben_von=nutzer_id,
        erstellt_von=nutzer_id,
    )
    db.session.add(buchung)
    db.session.flush()
    for zahlung, gebuehr in gebuehren:
        db.session.add(BuchungGebuehr(buchung_id=buchung.id, zahlung_id=zahlung.id))
        _neue_zahlung(buchung, zahlung.datum, gebuehr, zahlung.zahlungsart, nutzer_id)
    protokolliere(
        "gebuehren_erfasst",
        nutzer_id=nutzer_id,
        objekt_typ="buchung",
        objekt_id=buchung.id,
        details={"zahlungen": [z.id for z in gewaehlt], "betrag_cent": buchung.betrag_cent},
    )
    db.session.commit()
    return buchung


def suche_buchungen(filter: str = "ausgaben") -> list[Buchung]:
    abfrage = select(Buchung).where(Buchung.storno_von_id.is_(None))
    if filter == "ausgaben":
        abfrage = abfrage.where(Buchung.art == "ausgabe", Buchung.status == "festgeschrieben")
    elif filter == "einnahmen":
        abfrage = abfrage.where(Buchung.art == "einnahme", Buchung.status == "festgeschrieben")
    elif filter == "entwuerfe":
        abfrage = abfrage.where(Buchung.status == "entwurf")
    return list(
        db.session.execute(abfrage.order_by(Buchung.belegdatum.desc(), Buchung.id.desc())).scalars()
    )
