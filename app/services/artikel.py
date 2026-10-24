from sqlalchemy import func, or_, select

from app.extensions import db
from app.models import Artikel
from app.services.protokoll import protokolliere


class ArtikelnummerVergeben(ValueError):
    pass


def _bereinige(daten: dict) -> dict:
    sauber = {}
    for feld in Artikel.FELDER:
        wert = daten.get(feld)
        wert = wert.strip() if isinstance(wert, str) else wert
        sauber[feld] = None if wert == "" else wert
    return sauber


def _nummer_frei(artikelnummer: str | None, ausser_id: int | None = None) -> None:
    if not artikelnummer:
        return
    abfrage = select(Artikel.id).where(Artikel.artikelnummer == artikelnummer)
    if ausser_id is not None:
        abfrage = abfrage.where(Artikel.id != ausser_id)
    if db.session.execute(abfrage).first():
        raise ArtikelnummerVergeben("Diese Artikelnummer ist bereits vergeben.")


def lege_artikel_an(daten: dict, nutzer_id: int) -> Artikel:
    sauber = _bereinige(daten)
    _nummer_frei(sauber["artikelnummer"])
    artikel = Artikel(**sauber)
    db.session.add(artikel)
    db.session.flush()
    protokolliere(
        "artikel_angelegt", nutzer_id=nutzer_id, objekt_typ="artikel", objekt_id=artikel.id
    )
    db.session.commit()
    return artikel


def aendere_artikel(artikel: Artikel, daten: dict, nutzer_id: int) -> dict:
    neu = _bereinige(daten)
    _nummer_frei(neu["artikelnummer"], ausser_id=artikel.id)
    aenderungen = {}
    for feld, wert in neu.items():
        alt = getattr(artikel, feld)
        if alt != wert:
            aenderungen[feld] = {"alt": alt, "neu": wert}
            setattr(artikel, feld, wert)
    if aenderungen:
        protokolliere(
            "artikel_geaendert",
            nutzer_id=nutzer_id,
            objekt_typ="artikel",
            objekt_id=artikel.id,
            details=aenderungen,
        )
        db.session.commit()
    return aenderungen


def setze_archiviert(artikel: Artikel, archiviert: bool, nutzer_id: int) -> None:
    if artikel.archiviert == archiviert:
        return
    artikel.archiviert = archiviert
    protokolliere(
        "artikel_archiviert" if archiviert else "artikel_reaktiviert",
        nutzer_id=nutzer_id,
        objekt_typ="artikel",
        objekt_id=artikel.id,
    )
    db.session.commit()


def suche_artikel(text: str, filter: str = "alle", archiv: bool = False) -> list[Artikel]:
    abfrage = select(Artikel).where(Artikel.archiviert.is_(archiv))
    if filter == "produkte":
        abfrage = abfrage.where(Artikel.typ == "produkt")
    elif filter == "services":
        abfrage = abfrage.where(Artikel.typ == "service")

    text = text.strip()
    if text:
        muster = f"%{text}%"
        abfrage = abfrage.where(
            or_(
                Artikel.bezeichnung.ilike(muster),
                Artikel.beschreibung.ilike(muster),
                Artikel.artikelnummer.ilike(muster),
                Artikel.gtin.like(muster),
            )
        )
    return list(db.session.execute(abfrage.order_by(func.lower(Artikel.bezeichnung))).scalars())
