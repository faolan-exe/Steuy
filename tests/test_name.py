"""Das Projekt heißt steuy (früher taxCraft, Issue #42)."""

from pathlib import Path

WURZEL = Path(__file__).parent.parent
# Erlaubte Fundstellen: Schlüsselableitung (darf sich nie ändern) und alte Migrationen
ERLAUBT = {"app/services/geheimnis.py"}


def test_kein_alter_name_in_app_und_skripten():
    funde = []
    for ordner in ("app", "scripts", "docs/adr", ".github"):
        for datei in (WURZEL / ordner).rglob("*"):
            if not datei.is_file() or datei.suffix in {".pyc", ".png", ".jpg", ".woff2"}:
                continue
            pfad = str(datei.relative_to(WURZEL))
            if pfad in ERLAUBT:
                continue
            if "taxcraft" in datei.read_text(errors="ignore").lower():
                funde.append(pfad)
    assert funde == []


def test_schluesselableitung_unveraendert():
    """Ändert sich der Präfix, sind alle gespeicherten 2FA-Geheimnisse unlesbar."""
    text = (WURZEL / "app/services/geheimnis.py").read_text()
    assert '"taxcraft-geheimnis:"' in text


def test_oberflaeche_heisst_steuy(client):
    seite = client.get("/einrichtung").get_data(as_text=True)
    assert "steuy" in seite and "taxcraft" not in seite.lower()
