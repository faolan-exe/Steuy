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


def test_schalter_speichern_ohne_neu_laden(angemeldet, session, admin):
    """Mit fetch kommt JSON statt Weiterleitung (keine Meldung für die nächste Seite)."""
    kopf = {"X-Requested-With": "fetch"}
    for pfad, daten in (
        ("/profil/wochenmail", {}),
        ("/profil/hilfe", {"hilfe_anzeigen": "y"}),
        ("/einstellungen/zwei-faktor-pflicht", {}),
        ("/einstellungen/mahnwesen/automatik", {"auto_mahnen": "y"}),
        ("/einstellungen/update/automatik", {"an": "y"}),
    ):
        antwort = angemeldet.post(pfad, data=daten, headers=kopf)
        assert antwort.status_code == 200 and antwort.get_json()["ok"], pfad
    assert admin.wochenmail is False
    seite = angemeldet.get("/").get_data(as_text=True)
    assert "abbestellt" not in seite  # keine liegengebliebene Meldung


def test_rechnungseditor_positionen_ohne_neu_laden(angemeldet, admin, session):
    from app.services.rechnungen import neuer_entwurf

    entwurf = neuer_entwurf(admin.id)
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/bearbeiten").get_data(as_text=True)
    assert 'id="vorlage-artikel"' in seite and 'id="vorlage-text"' in seite
    assert 'data-neue-position="artikel"' in seite and "data-entfernen" in seite
    # Kundenanschrift wird dem Browser nicht zum Speichern angeboten (attrs nur aus Vorlagen)
    assert re.search(r'id="empfaenger_strasse"[^>]*autocomplete="off"', seite)
