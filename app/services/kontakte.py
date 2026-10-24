from datetime import date

from sqlalchemy import String, cast, func, or_, select

from app.domain.stammdaten import KUNDENNUMMER_START, LIEFERANTENNUMMER_START, naechste_nummer
from app.extensions import db
from app.models import Kontakt
from app.services.protokoll import protokolliere

TYPEN = {"kunde": (True, False), "lieferant": (False, True), "beides": (True, True)}


def _bereinige(daten: dict) -> dict:
    sauber = {}
    for feld in Kontakt.FELDER:
        wert = daten.get(feld)
        wert = wert.strip() if isinstance(wert, str) else wert
        sauber[feld] = wert or None
    sauber["land"] = sauber["land"] or "Deutschland"
    if sauber["email"]:
        sauber["email"] = sauber["email"].lower()
    # Nur die Namensfelder der gewählten Art behalten.
    if sauber["art"] == "firma":
        sauber.update(anrede=None, vorname=None, nachname=None)
    else:
        sauber["firmenname"] = None
    return sauber


def _vergib_nummern(kontakt: Kontakt) -> None:
    # Ohne Autoflush, sonst würde der halb geänderte Kontakt vor der Nummernvergabe gespeichert.
    with db.session.no_autoflush:
        if kontakt.ist_kunde and kontakt.kundennummer is None:
            hoechste = db.session.execute(select(func.max(Kontakt.kundennummer))).scalar()
            kontakt.kundennummer = naechste_nummer(hoechste, KUNDENNUMMER_START)
        if kontakt.ist_lieferant and kontakt.lieferantennummer is None:
            hoechste = db.session.execute(select(func.max(Kontakt.lieferantennummer))).scalar()
            kontakt.lieferantennummer = naechste_nummer(hoechste, LIEFERANTENNUMMER_START)


def typ_von(kontakt: Kontakt) -> str:
    if kontakt.ist_kunde and kontakt.ist_lieferant:
        return "beides"
    return "kunde" if kontakt.ist_kunde else "lieferant"


def lege_kontakt_an(daten: dict, nutzer_id: int) -> Kontakt:
    ist_kunde, ist_lieferant = TYPEN[daten["typ"]]
    kontakt = Kontakt(
        **_bereinige(daten),
        ist_kunde=ist_kunde,
        ist_lieferant=ist_lieferant,
        mahnsperre=bool(daten.get("mahnsperre")),
    )
    _vergib_nummern(kontakt)
    db.session.add(kontakt)
    db.session.flush()
    protokolliere(
        "kontakt_angelegt", nutzer_id=nutzer_id, objekt_typ="kontakt", objekt_id=kontakt.id
    )
    db.session.commit()
    return kontakt


def aendere_kontakt(kontakt: Kontakt, daten: dict, nutzer_id: int) -> list[str]:
    """Übernimmt Änderungen. Protokolliert nur die Feldnamen, keine Personendaten."""
    neu = _bereinige(daten)
    neu["ist_kunde"], neu["ist_lieferant"] = TYPEN[daten["typ"]]
    neu["mahnsperre"] = bool(daten.get("mahnsperre"))
    geaendert = sorted(feld for feld, wert in neu.items() if getattr(kontakt, feld) != wert)
    for feld in geaendert:
        setattr(kontakt, feld, neu[feld])
    if geaendert:
        _vergib_nummern(kontakt)
        protokolliere(
            "kontakt_geaendert",
            nutzer_id=nutzer_id,
            objekt_typ="kontakt",
            objekt_id=kontakt.id,
            details={"felder": geaendert},
        )
        db.session.commit()
    return geaendert


def setze_archiviert(kontakt: Kontakt, archiviert: bool, nutzer_id: int) -> None:
    if kontakt.archiviert == archiviert:
        return
    kontakt.archiviert = archiviert
    protokolliere(
        "kontakt_archiviert" if archiviert else "kontakt_reaktiviert",
        nutzer_id=nutzer_id,
        objekt_typ="kontakt",
        objekt_id=kontakt.id,
    )
    db.session.commit()


def suche_kontakte(text: str, filter: str = "alle", archiv: bool = False) -> list[Kontakt]:
    abfrage = select(Kontakt).where(Kontakt.archiviert.is_(archiv))
    if filter == "kunden":
        abfrage = abfrage.where(Kontakt.ist_kunde)
    elif filter == "lieferanten":
        abfrage = abfrage.where(Kontakt.ist_lieferant)

    text = text.strip()
    if text:
        muster = f"%{text}%"
        abfrage = abfrage.where(
            or_(
                *(
                    feld.ilike(muster)
                    for feld in (
                        Kontakt.firmenname,
                        Kontakt.vorname,
                        Kontakt.nachname,
                        Kontakt.ort,
                        Kontakt.email,
                    )
                ),
                cast(Kontakt.kundennummer, String).like(muster),
                cast(Kontakt.lieferantennummer, String).like(muster),
            )
        )

    sortname = func.lower(func.coalesce(Kontakt.firmenname, Kontakt.nachname))
    return list(db.session.execute(abfrage.order_by(sortname, Kontakt.vorname)).scalars())


def uebersicht(kontakt: Kontakt, heute: date | None = None) -> dict:
    """Alles zu einem Kontakt: Rechnungen, Angebote, Buchungen und was noch offen ist."""
    from app.domain.zahlung import ist_ueberfaellig
    from app.models import Buchung, Rechnung

    heute = heute or date.today()
    belege = list(
        db.session.execute(
            select(Rechnung)
            .where(Rechnung.kontakt_id == kontakt.id)
            .order_by(Rechnung.rechnungsdatum.desc(), Rechnung.id.desc())
        ).scalars()
    )
    rechnungen = [r for r in belege if r.belegart in ("rechnung", "korrektur")]
    angebote = [r for r in belege if r.belegart == "angebot"]
    buchungen = list(
        db.session.execute(
            select(Buchung)
            .where(Buchung.kontakt_id == kontakt.id)
            .order_by(Buchung.belegdatum.desc(), Buchung.id.desc())
        ).scalars()
    )
    offen = [r for r in rechnungen if r.offen_cent > 0]
    return {
        "rechnungen": rechnungen,
        "angebote": angebote,
        "buchungen": buchungen,
        "offen_cent": sum(r.offen_cent for r in offen),
        "anzahl_offen": len(offen),
        "ueberfaellig": [r for r in offen if ist_ueberfaellig(r.faellig_am, r.status, heute)],
        "umsatz_cent": sum(r.bezahlt_cent for r in rechnungen if not r.ist_entwurf),
        "offene_angebote": [a for a in angebote if a.status == "offen"],
        "zu_zahlen_cent": sum(b.offen_cent for b in buchungen if not b.ist_entwurf),
        "ausgaben_cent": sum(
            b.betrag_cent for b in buchungen if b.art == "ausgabe" and b.status == "festgeschrieben"
        ),
    }
