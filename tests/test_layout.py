"""Schutz vor Layoutfehlern, die beim Durchspielen auf dem Handy aufgefallen sind.

Echte Darstellung prüft kein Test. Diese Prüfungen sorgen nur dafür, dass die Regeln, die
die Fehler behoben haben, nicht versehentlich verschwinden.
"""

import re
from pathlib import Path

CSS = (Path(__file__).parent.parent / "app/web/static/css/app.css").read_text()


def regel(selektor: str) -> str:
    treffer = re.search(re.escape(selektor) + r"\s*\{([^}]*)\}", CSS)
    assert treffer, f"Regel {selektor} fehlt"
    return treffer.group(1)


def test_tabellenrahmen_klammert_unsichtbare_beschriftungen():
    """Der unsichtbare Text in Tabellenköpfen ist absolut positioniert. Ohne
    position: relative am Rahmen verbreitert er die ganze Seite (Nutzerverwaltung)."""
    inhalt = regel(".tabellenrahmen")
    assert "overflow-x: auto" in inhalt and "position: relative" in inhalt


def test_raster_kinder_duerfen_schrumpfen():
    """Sonst sprengt die Zahlungstabelle auf der Rechnungsseite das Handy-Layout."""
    assert re.search(r"\.raster-zwei > \*,\s*\.spalte > \*\s*\{\s*min-width: 0;", CSS)
    assert "minmax(0, 1fr)" in regel(".spalte")


def test_kopfleiste_bricht_auf_dem_handy_um():
    mobil = CSS[CSS.index("@media (max-width: 48rem)") :]
    assert "flex-wrap: wrap" in mobil and ".hauptnavi" in mobil
    assert "mask-image" in mobil  # Hinweis, dass die Navigation seitlich wischbar ist


def test_suche_ist_auf_dem_handy_sichtbar(angemeldet):
    seite = angemeldet.get("/").get_data(as_text=True)
    zeile = next(z for z in seite.splitlines() if 'aria-label="Suche"' in z)
    assert "optional" not in zeile  # „optional“ blendet das Symbol auf dem Handy aus
