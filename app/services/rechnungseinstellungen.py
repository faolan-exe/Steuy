from sqlalchemy import select

from app.domain.rechnung import formatiere_nummer
from app.extensions import db
from app.models import Gewerbe, Nummernkreis, Rechnung
from app.services.protokoll import protokolliere

GEWERBE_FELDER = (
    "kontoinhaber",
    "iban",
    "bic",
    "bank",
    "zahlungsziel_tage",
    "angebot_gueltig_tage",
    "hinweis_steuerbefreiung",
    "rechnung_einleitung",
    "rechnung_nachbemerkung",
    "e_rechnung",
)
KREIS_FELDER = ("praefix", "stellen", "naechste_nummer")


class NummerSchonVergeben(ValueError):
    pass


def rechnungskreis() -> Nummernkreis:
    return db.session.get(Nummernkreis, "rechnung")


def aendere_rechnungseinstellungen(gewerbe: Gewerbe, daten: dict, nutzer_id: int) -> dict:
    kreis = rechnungskreis()
    praefix = (daten.get("praefix") or "").strip()
    kandidat = formatiere_nummer(praefix, daten["naechste_nummer"], daten["stellen"])
    if db.session.execute(select(Rechnung.id).where(Rechnung.nummer == kandidat)).first():
        raise NummerSchonVergeben(f"Die Nummer {kandidat} ist schon vergeben.")

    aenderungen = {}
    for ziel, felder in ((gewerbe, GEWERBE_FELDER), (kreis, KREIS_FELDER)):
        for feld in felder:
            neu = daten.get(feld)
            if isinstance(neu, str):
                neu = neu.strip() or None
            if feld == "praefix":
                neu = praefix
            alt = getattr(ziel, feld)
            if alt != neu:
                aenderungen[feld] = {"alt": alt, "neu": neu}
                setattr(ziel, feld, neu)
    if aenderungen:
        protokolliere("rechnungseinstellungen_geaendert", nutzer_id=nutzer_id, details=aenderungen)
        db.session.commit()
    return aenderungen


def aendere_mail_einstellungen(gewerbe: Gewerbe, daten: dict, nutzer_id: int) -> list[str]:
    """Speichert den SMTP-Zugang. Leeres Passwort heißt: bisheriges behalten."""
    from app.services.geheimnis import verschluessele

    geaendert = []
    for feld in (
        "smtp_server",
        "smtp_port",
        "smtp_verschluesselung",
        "smtp_benutzer",
        "mail_absender",
    ):
        wert = daten.get(feld)
        if isinstance(wert, str):
            wert = wert.strip() or None
        if getattr(gewerbe, feld) != wert:
            setattr(gewerbe, feld, wert)
            geaendert.append(feld)
    if daten.get("smtp_passwort"):
        gewerbe.smtp_passwort = verschluessele(daten["smtp_passwort"])
        geaendert.append("smtp_passwort")
    if daten.get("passwort_loeschen") and gewerbe.smtp_passwort:
        gewerbe.smtp_passwort = None
        geaendert.append("smtp_passwort")
    if geaendert:
        # Nur die Feldnamen ins Protokoll, nie das Passwort
        protokolliere("mail_einstellungen", nutzer_id=nutzer_id, details={"felder": geaendert})
    db.session.commit()
    return geaendert
