"""Belege hochladen, auslesen, verwerfen."""

import io
from dataclasses import asdict
from datetime import date

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import func, select

from app.domain.belegerkennung import Vorschlag, aus_text
from app.domain.datei import TYPEN, erkenne_typ
from app.domain.erechnung import XML_ANHAENGE, ERechnungFehler, aus_xml
from app.extensions import db
from app.models import Beleg, Kontakt
from app.services import ablage, texterkennung
from app.services.protokoll import protokolliere

MAX_GROESSE = 20 * 1024 * 1024


class BelegUngueltig(ValueError):
    pass


class BelegVorhanden(ValueError):
    def __init__(self, beleg: Beleg):
        super().__init__(f"Diese Datei wurde bereits hochgeladen ({beleg.dateiname}).")
        self.beleg = beleg


def _pdf_auslesen(inhalt: bytes) -> tuple[str | None, Vorschlag | None]:
    try:
        reader = PdfReader(io.BytesIO(inhalt))
        for name, daten in reader.attachments.items():
            if name.lower() in XML_ANHAENGE:
                try:
                    return None, aus_xml(daten[0])
                except ERechnungFehler:
                    pass
        text = "\n".join(seite.extract_text() or "" for seite in reader.pages[:5]).strip()
    except (PdfReadError, ValueError, KeyError):
        return None, None
    if len(text) < 20:
        return text or None, None  # vermutlich ein Scan, Texterkennung folgt
    return text, aus_text(text)


def lies_aus(mime: str, inhalt: bytes) -> tuple[str | None, Vorschlag | None]:
    """E-Rechnung > PDF-Text > Texterkennung (OCR) für Fotos und Scans."""
    if mime == "application/xml":
        try:
            return None, aus_xml(inhalt)
        except ERechnungFehler:
            return None, None
    if mime == "application/pdf":
        text, vorschlag = _pdf_auslesen(inhalt)
        if vorschlag:
            return text, vorschlag
    erkannt = texterkennung.erkenne(mime, inhalt)
    if erkannt:
        return erkannt, aus_text(erkannt, quelle="ocr")
    return None, None


def _als_json(vorschlag: Vorschlag | None) -> dict | None:
    if vorschlag is None:
        return None
    daten = asdict(vorschlag)
    if daten["datum"]:
        daten["datum"] = daten["datum"].isoformat()
    return daten


def lade_hoch(dateiname: str, inhalt: bytes, nutzer_id: int) -> Beleg:
    if not inhalt:
        raise BelegUngueltig(f"{dateiname}: Die Datei ist leer.")
    if len(inhalt) > MAX_GROESSE:
        raise BelegUngueltig(f"{dateiname}: Die Datei ist größer als 20 MB.")
    mime = erkenne_typ(inhalt)
    if mime not in TYPEN:
        raise BelegUngueltig(f"{dateiname}: Nur PDF, JPG, PNG und XML (E-Rechnung) sind erlaubt.")

    sha256 = ablage.speichere(inhalt)
    vorhanden = db.session.execute(select(Beleg).where(Beleg.sha256 == sha256)).scalar_one_or_none()
    if vorhanden:
        raise BelegVorhanden(vorhanden)

    text, vorschlag = lies_aus(mime, inhalt)
    beleg = Beleg(
        sha256=sha256,
        dateiname=(dateiname or "beleg")[:255],
        mime=mime,
        groesse=len(inhalt),
        text=text,
        vorschlag=_als_json(vorschlag),
        hochgeladen_von=nutzer_id,
    )
    db.session.add(beleg)
    db.session.flush()
    protokolliere(
        "beleg_hochgeladen",
        nutzer_id=nutzer_id,
        objekt_typ="beleg",
        objekt_id=beleg.id,
        details={"sha256": sha256, "dateiname": beleg.dateiname},
    )
    db.session.commit()
    return beleg


def setze_text(beleg: Beleg, text: str | None, vorschlag: Vorschlag | None) -> None:
    """Für die nachträgliche Texterkennung. Die Datei selbst bleibt unverändert."""
    beleg.text = text
    beleg.vorschlag = _als_json(vorschlag)
    db.session.commit()


def verwerfe(beleg: Beleg, nutzer_id: int) -> None:
    if beleg.verbucht:
        raise BelegUngueltig("Verbuchte Belege können nicht verworfen werden. Bitte stornieren.")
    beleg.verworfen = True
    protokolliere("beleg_verworfen", nutzer_id=nutzer_id, objekt_typ="beleg", objekt_id=beleg.id)
    db.session.commit()


def vorschlag_fuer_formular(beleg: Beleg) -> dict:
    """Formular-Vorbelegung aus dem Vorschlag, Lieferant wenn möglich als Kontakt."""
    v = beleg.vorschlag or {}
    daten = {
        "partner": v.get("lieferant"),
        "belegnummer": v.get("belegnummer"),
        "belegdatum": date.fromisoformat(v["datum"]) if v.get("datum") else None,
        "betrag_cent": v.get("betrag_cent"),
        "hinweis": v.get("hinweis"),
        "quelle": v.get("quelle"),
    }
    if daten["partner"]:
        kontakt = db.session.execute(
            select(Kontakt).where(
                func.lower(Kontakt.firmenname) == daten["partner"].lower(),
                Kontakt.archiviert.is_(False),
            )
        ).scalar_one_or_none()
        if kontakt:
            daten["kontakt_id"] = kontakt.id
    return daten


def neue_belege() -> list[Beleg]:
    alle = db.session.execute(
        select(Beleg).where(Beleg.verworfen.is_(False)).order_by(Beleg.hochgeladen_am.desc())
    ).scalars()
    return [b for b in alle if not b.buchungen]
