from app.extensions import db
from app.models import Gewerbe
from app.services.einrichtung import bereinige_firmendaten
from app.services.protokoll import protokolliere


def aendere_firmendaten(gewerbe: Gewerbe, daten: dict, nutzer_id: int) -> dict:
    """Übernimmt geänderte Felder und protokolliert alt und neu. Gibt die Änderungen zurück."""
    aenderungen = {}
    for feld, neu in bereinige_firmendaten(daten).items():
        alt = getattr(gewerbe, feld)
        if alt != neu:
            aenderungen[feld] = {"alt": alt, "neu": neu}
            setattr(gewerbe, feld, neu)

    if aenderungen:
        protokolliere(
            "firmendaten_geaendert",
            nutzer_id=nutzer_id,
            objekt_typ="gewerbe",
            objekt_id=gewerbe.id,
            details=aenderungen,
        )
        db.session.commit()
    return aenderungen
