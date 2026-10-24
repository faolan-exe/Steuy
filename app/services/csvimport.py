"""Kontakte und Artikel aus einer CSV-Datei übernehmen (z. B. beim Umstieg von Lexware Office)."""

from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.domain.csvimport import CsvUngueltig, artikel_aus, kontakt_aus, leer
from app.extensions import db
from app.models import Artikel, Kontakt
from app.services.kontakte import TYPEN, _vergib_nummern
from app.services.kontakte import _bereinige as bereinige_kontakt
from app.services.protokoll import protokolliere


@dataclass
class Ergebnis:
    neu: int = 0
    doppelt: list[tuple[int, str]] = field(default_factory=list)
    fehler: list[tuple[int, str]] = field(default_factory=list)


def _nummer_frei(spalte, nummer: int | None) -> int | None:
    if nummer is None:
        return None
    return None if db.session.execute(select(spalte).where(spalte == nummer)).first() else nummer


def _kontakt_doppelt(daten: dict) -> str | None:
    """Gleiche E-Mail, oder gleiche Nummer mit gleichem Namen (z. B. Datei doppelt importiert).
    Ist nur die Nummer schon vergeben, bekommt der Kontakt einfach eine neue."""
    if (
        daten.get("email")
        and db.session.execute(
            select(Kontakt.id).where(func.lower(Kontakt.email) == daten["email"].lower())
        ).first()
    ):
        return f"E-Mail {daten['email']} gibt es schon"
    for feld, spalte in (
        ("kundennummer", Kontakt.kundennummer),
        ("lieferantennummer", Kontakt.lieferantennummer),
    ):
        nummer = daten.get(feld)
        vorhanden = (
            db.session.execute(select(Kontakt).where(spalte == nummer)).scalar_one_or_none()
            if nummer is not None
            else None
        )
        if vorhanden and (vorhanden.firmenname, vorhanden.nachname) == (
            daten.get("firmenname"),
            daten.get("nachname") if not daten.get("firmenname") else None,
        ):
            return f"{vorhanden.name} mit Nummer {nummer} gibt es schon"
    return None


def importiere_kontakte(
    zeilen: list[list[str]], zuordnung: dict, typ: str, nutzer_id: int, pruefen: bool = False
) -> Ergebnis:
    """Mit pruefen=True wird nichts gespeichert, nur gezählt (Vorschau)."""
    ergebnis = Ergebnis()
    ist_kunde, ist_lieferant = TYPEN[typ]
    for nr, zeile in enumerate(zeilen, start=2):  # Zeile 1 ist die Kopfzeile
        if leer(zeile):
            continue
        try:
            daten = kontakt_aus(zeile, zuordnung, typ)
        except CsvUngueltig as fehler:
            ergebnis.fehler.append((nr, str(fehler)))
            continue
        grund = _kontakt_doppelt(daten)
        if grund:
            ergebnis.doppelt.append((nr, grund))
            continue
        kontakt = Kontakt(
            **bereinige_kontakt(daten),
            ist_kunde=ist_kunde,
            ist_lieferant=ist_lieferant,
            # Nummern aus dem alten Programm behalten, wenn sie frei sind
            kundennummer=_nummer_frei(Kontakt.kundennummer, daten["kundennummer"])
            if ist_kunde
            else None,
            lieferantennummer=(
                _nummer_frei(Kontakt.lieferantennummer, daten["lieferantennummer"])
                if ist_lieferant
                else None
            ),
        )
        _vergib_nummern(kontakt)
        db.session.add(kontakt)
        db.session.flush()
        ergebnis.neu += 1
    _abschluss("kontakte", ergebnis, nutzer_id, pruefen)
    return ergebnis


def importiere_artikel(
    zeilen: list[list[str]], zuordnung: dict, nutzer_id: int, pruefen: bool = False
) -> Ergebnis:
    ergebnis = Ergebnis()
    for nr, zeile in enumerate(zeilen, start=2):
        if leer(zeile):
            continue
        try:
            daten = artikel_aus(zeile, zuordnung)
        except CsvUngueltig as fehler:
            ergebnis.fehler.append((nr, str(fehler)))
            continue
        nummer = daten.get("artikelnummer")
        if (
            nummer
            and db.session.execute(
                select(Artikel.id).where(Artikel.artikelnummer == nummer)
            ).first()
        ):
            ergebnis.doppelt.append((nr, f"Artikelnummer {nummer} gibt es schon"))
            continue
        db.session.add(Artikel(**{f: daten.get(f) for f in Artikel.FELDER}))
        db.session.flush()
        ergebnis.neu += 1
    _abschluss("artikel", ergebnis, nutzer_id, pruefen)
    return ergebnis


def _abschluss(art: str, ergebnis: Ergebnis, nutzer_id: int, pruefen: bool) -> None:
    if pruefen:
        db.session.rollback()
        return
    protokolliere(
        "csv_import",
        nutzer_id=nutzer_id,
        details={
            "art": art,
            "neu": ergebnis.neu,
            "doppelt": len(ergebnis.doppelt),
            "fehler": len(ergebnis.fehler),
        },
    )
    db.session.commit()
