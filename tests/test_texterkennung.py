import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from app.models import Beleg
from app.services import texterkennung

ohne_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="Tesseract ist nicht installiert"
)

BELEG = [
    "Muster Baumarkt GmbH",
    "Rechnung Nr. 2026-555",
    "Datum: 14.10.2026",
    "Schrauben        12,40",
    "Gesamtbetrag     23,80 EUR",
]


def belegfoto(format="PNG") -> bytes:
    bild = Image.new("RGB", (1400, 700), "white")
    zeichnen = ImageDraw.Draw(bild)
    schrift = ImageFont.load_default(size=48)
    for i, zeile in enumerate(BELEG):
        zeichnen.text((60, 60 + i * 110), zeile, fill="black", font=schrift)
    puffer = io.BytesIO()
    bild.save(puffer, format=format)
    return puffer.getvalue()


def scan_pdf() -> bytes:
    puffer = io.BytesIO()
    Image.open(io.BytesIO(belegfoto())).save(puffer, format="PDF", resolution=150)
    return puffer.getvalue()


@ohne_tesseract
@pytest.mark.parametrize(
    ("mime", "inhalt"),
    [
        ("image/png", belegfoto),
        ("image/jpeg", lambda: belegfoto("JPEG")),
        ("application/pdf", scan_pdf),
    ],
)
def test_foto_und_scan(app, mime, inhalt):
    with app.app_context():
        text = texterkennung.erkenne(mime, inhalt())
    assert "Baumarkt" in text
    assert "23,80" in text


@ohne_tesseract
def test_upload_foto_fuellt_vor(angemeldet, session):
    angemeldet.post(
        "/belege/hochladen",
        data={"dateien": [(io.BytesIO(belegfoto()), "kassenzettel.png")]},
        content_type="multipart/form-data",
    )
    beleg = session.execute(select(Beleg)).scalar_one()
    assert beleg.vorschlag["quelle"] == "ocr"
    assert beleg.vorschlag["betrag_cent"] == 2380
    assert beleg.vorschlag["belegnummer"] == "2026-555"
    seite = angemeldet.get(f"/belege/{beleg.id}").get_data(as_text=True)
    assert "aus der Texterkennung vorausgefüllt" in seite


def test_abschaltbar(app):
    app.config["TEXTERKENNUNG"] = False
    try:
        with app.app_context():
            assert texterkennung.erkenne("image/png", belegfoto()) is None
    finally:
        app.config["TEXTERKENNUNG"] = True


def test_kaputtes_bild(app):
    with app.app_context():
        assert texterkennung.erkenne("image/png", b"\x89PNG\r\n\x1a\nkaputt") is None


def test_ohne_tesseract(app, monkeypatch):
    monkeypatch.setattr(texterkennung.shutil, "which", lambda _: None)
    with app.app_context():
        assert texterkennung.erkenne("image/png", belegfoto()) is None
