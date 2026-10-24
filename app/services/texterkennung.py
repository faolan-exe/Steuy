"""Texterkennung (OCR) für Belegfotos und gescannte PDFs, lokal mit Tesseract.

Ohne installiertes Tesseract liefert die Erkennung einfach keinen Text. Der Rest von
steuy funktioniert dann unverändert, nur ohne Vorschläge für Fotos und Scans.
"""

import io
import shutil
from functools import cache

import pypdfium2
import pytesseract
from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SEITEN = 3
MAX_KANTE = 3000  # Pixel, größere Fotos werden verkleinert
ZEITLIMIT = 30  # Sekunden je Seite


def verfuegbar() -> bool:
    return (
        bool(current_app.config.get("TEXTERKENNUNG", True))
        and shutil.which(pytesseract.pytesseract.tesseract_cmd) is not None
    )


@cache
def _sprachen() -> str:
    vorhanden = set(pytesseract.get_languages(config=""))
    gewuenscht = [s for s in ("deu", "eng") if s in vorhanden]
    return "+".join(gewuenscht) or "eng"


def _vorbereiten(bild: Image.Image) -> Image.Image:
    bild = ImageOps.exif_transpose(bild).convert("L")  # Handyfotos richtig drehen, Graustufen
    if max(bild.size) > MAX_KANTE:
        bild.thumbnail((MAX_KANTE, MAX_KANTE))
    return bild


def _ocr(bild: Image.Image) -> str:
    return pytesseract.image_to_string(_vorbereiten(bild), lang=_sprachen(), timeout=ZEITLIMIT)


def erkenne(mime: str, inhalt: bytes) -> str | None:
    if not verfuegbar():
        return None
    try:
        if mime.startswith("image/"):
            text = _ocr(Image.open(io.BytesIO(inhalt)))
        elif mime == "application/pdf":
            pdf = pypdfium2.PdfDocument(inhalt)
            seiten = []
            for i in range(min(len(pdf), MAX_SEITEN)):
                bild = pdf[i].render(scale=300 / 72).to_pil()
                seiten.append(_ocr(bild))
            text = "\n".join(seiten)
        else:
            return None
    except (UnidentifiedImageError, pypdfium2.PdfiumError, RuntimeError, OSError):
        current_app.logger.warning("Texterkennung fehlgeschlagen", exc_info=True)
        return None
    text = text.strip()
    return text or None
