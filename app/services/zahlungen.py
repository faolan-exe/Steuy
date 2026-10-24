"""Zahlungseingänge erfassen, rückgängig machen, offene Punkte sammeln."""

from datetime import date

from sqlalchemy import extract, func, select

from app.domain.buchung import betrieblicher_anteil
from app.domain.datei import erkenne_typ
from app.domain.zahlung import (
    ZahlungUngueltig,
    ist_ueberfaellig,
    pruefe_zahlung,
    status_nach_zahlungen,
)
from app.extensions import db
from app.models import Buchung, Rechnung, Zahlung
from app.services import ablage
from app.services.protokoll import protokolliere


def _aktualisiere_status(rechnung: Rechnung) -> None:
    db.session.flush()
    db.session.refresh(rechnung, ["zahlungen"])
    rechnung.status = status_nach_zahlungen(rechnung.summe_cent, rechnung.bezahlt_cent)


NACHWEIS_TYPEN = {"application/pdf", "image/png", "image/jpeg"}
NACHWEIS_MAX = 20 * 1024 * 1024


def _pruefe_nachweis(inhalt: bytes) -> str:
    """Zahlungsnachweis (Kontoauszug, PayPal-Beleg): Typ am Inhalt erkennen, nicht am Namen."""
    if not inhalt:
        raise ZahlungUngueltig("Die Datei für den Nachweis ist leer.")
    if len(inhalt) > NACHWEIS_MAX:
        raise ZahlungUngueltig("Der Nachweis ist größer als 20 MB.")
    mime = erkenne_typ(inhalt)
    if mime not in NACHWEIS_TYPEN:
        raise ZahlungUngueltig("Als Nachweis sind nur PDF, JPG und PNG erlaubt.")
    return mime


def erfasse_zahlung(
    rechnung: Rechnung,
    *,
    datum: date,
    betrag_cent: int,
    zahlungsart: str,
    angekommen_cent: int | None,
    notiz: str | None,
    nutzer_id: int,
    referenz: str | None = None,
    nachweis: tuple[str, bytes] | None = None,
) -> Zahlung:
    if not rechnung.ist_rechnung or rechnung.ist_entwurf or rechnung.status == "storniert":
        raise ZahlungUngueltig(
            "Zahlungen gibt es nur zu finalisierten, nicht stornierten Rechnungen."
        )
    pruefe_zahlung(
        betrag_cent=betrag_cent,
        offen_cent=rechnung.offen_cent,
        angekommen_cent=angekommen_cent,
        datum=datum,
        rechnungsdatum=rechnung.rechnungsdatum,
    )
    zahlung = Zahlung(
        rechnung_id=rechnung.id,
        datum=datum,
        betrag_cent=betrag_cent,
        angekommen_cent=angekommen_cent,
        zahlungsart=zahlungsart,
        notiz=(notiz or "").strip() or None,
        referenz=(referenz or "").strip()[:100] or None,
        erfasst_von=nutzer_id,
    )
    if nachweis:
        name, inhalt = nachweis
        zahlung.nachweis_mime = _pruefe_nachweis(inhalt)
        zahlung.nachweis_sha256 = ablage.speichere(inhalt)
        zahlung.nachweis_name = (name or "nachweis")[:255]
    db.session.add(zahlung)
    _aktualisiere_status(rechnung)
    protokolliere(
        "zahlung_erfasst",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={
            "zahlung_id": zahlung.id,
            "datum": datum.isoformat(),
            "betrag_cent": betrag_cent,
            "zahlungsart": zahlungsart,
        },
    )
    db.session.commit()
    return zahlung


def storniere_zahlung(zahlung: Zahlung, nutzer_id: int) -> Zahlung:
    """Gegenbuchung mit gleichem Datum, damit sich beide im selben Zeitraum aufheben."""
    if zahlung.storno_von_id is not None:
        raise ZahlungUngueltig("Eine Gegenbuchung kann nicht rückgängig gemacht werden.")
    vorhanden = db.session.execute(
        select(Zahlung.id).where(Zahlung.storno_von_id == zahlung.id)
    ).first()
    if vorhanden:
        raise ZahlungUngueltig("Diese Zahlung wurde bereits rückgängig gemacht.")

    storno = Zahlung(
        rechnung_id=zahlung.rechnung_id,
        datum=zahlung.datum,
        betrag_cent=-zahlung.betrag_cent,
        angekommen_cent=None,
        zahlungsart=zahlung.zahlungsart,
        notiz="Rückgängig gemacht",
        storno_von_id=zahlung.id,
        erfasst_von=nutzer_id,
    )
    db.session.add(storno)
    _aktualisiere_status(zahlung.rechnung)
    protokolliere(
        "zahlung_storniert",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=zahlung.rechnung_id,
        details={"zahlung_id": zahlung.id, "betrag_cent": zahlung.betrag_cent},
    )
    db.session.commit()
    return storno


def ist_storniert(zahlung: Zahlung) -> bool:
    return any(z.storno_von_id == zahlung.id for z in zahlung.rechnung.zahlungen)


def zu_pruefen(heute: date | None = None) -> dict:
    """Alles, was noch eine Entscheidung braucht (docs/domain/zahlungen-und-pruefung.md)."""
    heute = heute or date.today()
    offene = list(
        db.session.execute(
            select(Rechnung)
            .where(Rechnung.status.in_(["offen", "teilbezahlt"]), Rechnung.belegart == "rechnung")
            .order_by(Rechnung.faellig_am, Rechnung.id)
        ).scalars()
    )
    ueberfaellig = [r for r in offene if ist_ueberfaellig(r.faellig_am, r.status, heute)]
    entwuerfe = list(
        db.session.execute(
            select(Rechnung).where(Rechnung.status == "entwurf").order_by(Rechnung.erstellt_am)
        ).scalars()
    )
    from app.services.belege import neue_belege
    from app.services.buchungen import offene_gebuehren, suche_buchungen
    from app.services.mahnwesen import faellige_mahnungen

    mahnungen = faellige_mahnungen(heute)

    gebuehren = offene_gebuehren()
    belege = neue_belege()
    buchungsentwuerfe = suche_buchungen("entwuerfe")
    offene_ausgaben = [
        b for b in suche_buchungen("ausgaben") if b.zahlstatus in ("offen", "teilbezahlt")
    ]
    offene_einnahmen = [
        b for b in suche_buchungen("einnahmen") if b.zahlstatus in ("offen", "teilbezahlt")
    ]
    angebote = list(
        db.session.execute(
            select(Rechnung)
            .where(Rechnung.belegart == "angebot", Rechnung.status == "offen")
            .order_by(Rechnung.gueltig_bis)
        ).scalars()
    )
    from app.services.jahreswechsel import kandidaten
    from app.services.shop import offene_hinweise, zur_freigabe

    jahreswechsel = kandidaten(heute)
    shop_freigabe = zur_freigabe()
    shop_hinweise = offene_hinweise()
    return {
        "jahreswechsel": jahreswechsel,
        "shop_freigabe": shop_freigabe,
        "shop_hinweise": shop_hinweise,
        "angebote": angebote,
        "mahnungen": mahnungen,
        "ueberfaellig": ueberfaellig,
        "offen": [r for r in offene if r not in ueberfaellig],
        "entwuerfe": entwuerfe,
        "gebuehren": gebuehren,
        "belege": belege,
        "buchungsentwuerfe": buchungsentwuerfe,
        "offene_ausgaben": offene_ausgaben,
        "offene_einnahmen": offene_einnahmen,
        "anzahl": len(offene)
        + len(jahreswechsel)
        + len(shop_freigabe)
        + len(shop_hinweise)
        + len(entwuerfe)
        + len(gebuehren)
        + len(mahnungen)
        + len(belege)
        + len(buchungsentwuerfe)
        + len(offene_ausgaben)
        + len(offene_einnahmen)
        + len(angebote),
    }


def kennzahlen(jahr: int) -> dict:
    """Einnahmen und Ausgaben nach Zahlungsdatum (Zuflussprinzip, docs/domain/euer.md).

    Bei Buchungen zählt nur der betriebliche Anteil.
    """
    einnahmen = [0] * 12
    ausgaben = [0] * 12
    zahlungen = db.session.execute(
        select(Zahlung).where(extract("year", Zahlung.datum) == jahr)
    ).scalars()
    for z in zahlungen:
        monat = z.datum.month - 1
        if z.rechnung_id is not None:
            einnahmen[monat] += z.betrag_cent
        else:
            anteil = betrieblicher_anteil(z.betrag_cent, z.buchung.betrieblich_prozent)
            (einnahmen if z.buchung.art == "einnahme" else ausgaben)[monat] += anteil
    offene = db.session.execute(
        select(Rechnung).where(
            Rechnung.status.in_(["offen", "teilbezahlt"]), Rechnung.belegart == "rechnung"
        )
    ).scalars()
    anzahl = db.session.execute(
        select(func.count())
        .select_from(Rechnung)
        .where(
            Rechnung.finalisiert_am.is_not(None),
            Rechnung.belegart == "rechnung",
            Rechnung.status != "storniert",
            extract("year", Rechnung.rechnungsdatum) == jahr,
        )
    ).scalar_one()
    anzahl_angebote = db.session.execute(
        select(func.count())
        .select_from(Rechnung)
        .where(
            Rechnung.finalisiert_am.is_not(None),
            Rechnung.belegart == "angebot",
            extract("year", Rechnung.rechnungsdatum) == jahr,
        )
    ).scalar_one()
    return {
        "anzahl_angebote": anzahl_angebote,
        "einnahmen_cent": sum(einnahmen),
        "einnahmen_monate": einnahmen,
        "ausgaben_cent": sum(ausgaben),
        "ausgaben_monate": ausgaben,
        "offen_cent": sum(r.offen_cent for r in offene),
        "anzahl_rechnungen": anzahl,
    }


def rechnungsstand(jahr: int, heute: date | None = None) -> dict:
    """Für das Kreisdiagramm: geschriebene Rechnungen eines Jahres nach Zustand.

    Zählt Rechnungen aus steuy und übernommene Einnahmen (z. B. aus Lexware). Bei übernommenen
    Einnahmen ist keine Fälligkeit bekannt, sie zählen offen oder bezahlt. `gesamt_alle` zählt
    über alle Jahre (für die Meilensteine)."""
    heute = heute or date.today()
    stand = {"gesamt": 0, "bezahlt": 0, "offen": 0, "ueberfaellig": 0, "gesamt_alle": 0}
    rechnungen = db.session.execute(
        select(Rechnung).where(
            Rechnung.belegart == "rechnung",
            Rechnung.status.notin_(["entwurf", "storniert"]),
        )
    ).scalars()
    for r in rechnungen:
        stand["gesamt_alle"] += 1
        if r.rechnungsdatum.year != jahr:
            continue
        stand["gesamt"] += 1
        if r.status == "bezahlt" or r.offen_cent <= 0:
            stand["bezahlt"] += 1
        elif ist_ueberfaellig(r.faellig_am, r.status, heute):
            stand["ueberfaellig"] += 1
        else:
            stand["offen"] += 1
    einnahmen = db.session.execute(
        select(Buchung).where(
            Buchung.art == "einnahme",
            Buchung.status == "festgeschrieben",
            Buchung.storno_von_id.is_(None),
        )
    ).scalars()
    for b in einnahmen:
        if b.zahlstatus == "storniert":
            continue
        stand["gesamt_alle"] += 1
        if b.belegdatum.year != jahr:
            continue
        stand["gesamt"] += 1
        stand["bezahlt" if b.zahlstatus == "bezahlt" else "offen"] += 1
    return stand


def jahre_mit_daten(heute: date | None = None) -> list[int]:
    """Jahre, für die es Zahlungen, Buchungen oder Rechnungen gibt (neueste zuerst).

    Das laufende Jahr steht immer dabei, auch wenn es noch keine Daten gibt."""
    heute = heute or date.today()
    jahre = {heute.year}
    for spalte, filter_ in (
        (Zahlung.datum, None),
        (Buchung.belegdatum, None),
        (Rechnung.rechnungsdatum, Rechnung.status != "entwurf"),
    ):
        abfrage = select(extract("year", spalte)).distinct()
        if filter_ is not None:
            abfrage = abfrage.where(filter_)
        jahre.update(int(j) for j in db.session.execute(abfrage).scalars() if j)
    return sorted(jahre, reverse=True)
