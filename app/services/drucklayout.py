"""Drucklayout lesen und speichern, Logo ablegen."""

import base64
import io
from dataclasses import asdict

from PIL import Image, UnidentifiedImageError

from app.domain.datei import erkenne_typ
from app.domain.drucklayout import Layout, feldnamen
from app.extensions import db
from app.models import Drucklayout
from app.services import ablage
from app.services.protokoll import protokolliere

MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_LOGO_PIXEL = 6000
LOGO_BASISHOEHE_MM = 12


class LogoUngueltig(ValueError):
    pass


def _zeile() -> Drucklayout:
    zeile = db.session.get(Drucklayout, 1)
    if zeile is None:
        zeile = Drucklayout(id=1)
        db.session.add(zeile)
        db.session.flush()
    return zeile


def aktuell() -> Layout:
    zeile = _zeile()
    return Layout(**{name: getattr(zeile, name) for name in feldnamen()})


def speichere(layout: Layout, nutzer_id: int) -> None:
    zeile = _zeile()
    for name, wert in asdict(layout).items():
        setattr(zeile, name, wert)
    protokolliere("drucklayout_gespeichert", nutzer_id=nutzer_id, details={"layout": layout.layout})
    db.session.commit()


def zuruecksetzen(nutzer_id: int) -> None:
    speichere(Layout(), nutzer_id)


def setze_logo(inhalt: bytes, nutzer_id: int) -> None:
    """Nur PNG und JPEG (kein SVG: darin könnten Skripte stehen), bis 2 MB."""
    if not inhalt:
        raise LogoUngueltig("Die Datei ist leer.")
    if len(inhalt) > MAX_LOGO_BYTES:
        raise LogoUngueltig("Das Logo ist größer als 2 MB.")
    mime = erkenne_typ(inhalt)
    if mime not in ("image/png", "image/jpeg"):
        raise LogoUngueltig("Bitte ein Logo als PNG oder JPG hochladen.")
    try:
        with Image.open(io.BytesIO(inhalt)) as bild:
            breite, hoehe = bild.size
            bild.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as fehler:
        raise LogoUngueltig("Das Bild ist beschädigt oder kein gültiges PNG/JPG.") from fehler
    if max(breite, hoehe) > MAX_LOGO_PIXEL:
        raise LogoUngueltig(f"Das Logo ist zu groß (höchstens {MAX_LOGO_PIXEL} Pixel Kantenlänge).")
    zeile = _zeile()
    zeile.logo_sha256 = ablage.speichere(inhalt)
    zeile.logo_mime = mime
    protokolliere("logo_gesetzt", nutzer_id=nutzer_id, details={"sha256": zeile.logo_sha256})
    db.session.commit()


def entferne_logo(nutzer_id: int) -> None:
    zeile = _zeile()
    zeile.logo_sha256 = None
    zeile.logo_mime = None
    protokolliere("logo_entfernt", nutzer_id=nutzer_id)
    db.session.commit()


def logo_daten_uri() -> str | None:
    """Das Logo als data:-Adresse, damit das PDF ohne weitere Dateien entsteht."""
    zeile = _zeile()
    if not zeile.logo_sha256:
        return None
    try:
        inhalt = ablage.lies(zeile.logo_sha256)
    except (ablage.AblageBeschaedigt, OSError):
        return None
    return f"data:{zeile.logo_mime};base64," + base64.b64encode(inhalt).decode()


def logo_hoehe_mm(layout: Layout) -> float:
    return round(LOGO_BASISHOEHE_MM * layout.logo_prozent / 100, 1)
