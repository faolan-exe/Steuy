"""Wann ist welche Mahnstufe fällig? (docs/domain/mahnwesen.md)"""

from dataclasses import dataclass
from datetime import date, timedelta

# Verzugspauschale nach § 288 Abs. 5 BGB, nur gegenüber Schuldnern, die keine Verbraucher sind
VERZUGSPAUSCHALE_CENT = 4000
PAUSCHALE_AB_STUFE = 2
TEXT_MAX = 3000

# Vorgefertigte Brieftexte je Stufe. Dieselben Texte setzt die Migration als Startwert.
STANDARDTEXTE = {
    1: (
        "Guten Tag,\n\n"
        "sicher ist es Ihnen im Alltag nur entgangen: Für die Rechnung {nummer} vom "
        "{rechnungsdatum} habe ich noch keinen Zahlungseingang festgestellt.\n\n"
        "Bitte überweisen Sie den offenen Betrag bis zum {frist}. Vielen Dank!"
    ),
    2: (
        "Guten Tag,\n\n"
        "trotz meiner Zahlungserinnerung ist die Rechnung {nummer} vom {rechnungsdatum} noch "
        "offen. Sie war am {faellig} fällig.\n\n"
        "Bitte überweisen Sie den unten genannten Betrag bis spätestens {frist}. Geht bis dahin "
        "keine Zahlung ein, mahne ich erneut und behalte mir vor, Verzugszinsen zu berechnen."
    ),
    3: (
        "Guten Tag,\n\n"
        "trotz Zahlungserinnerung und Mahnung habe ich zur Rechnung {nummer} vom "
        "{rechnungsdatum} noch keine vollständige Zahlung erhalten. Dies ist meine letzte "
        "Mahnung.\n\n"
        "Bitte überweisen Sie den unten genannten Betrag bis spätestens {frist}. Geht das Geld "
        "bis dahin nicht ein, behalte ich mir ohne weitere Ankündigung rechtliche Schritte vor, "
        "zum Beispiel ein gerichtliches Mahnverfahren. Dadurch können weitere Kosten für Sie "
        "entstehen.\n\n"
        "Gibt es einen Grund, warum Sie noch nicht zahlen konnten, melden Sie sich bitte "
        "vorher bei mir."
    ),
}

PLATZHALTER = {
    "nummer": "Rechnungsnummer",
    "rechnungsdatum": "Rechnungsdatum",
    "faellig": "Fälligkeit der Rechnung",
    "frist": "neue Zahlungsfrist",
    "betrag": "offener Rechnungsbetrag",
    "gesamt": "zu zahlender Betrag mit Verzugspauschale",
}


def fuelle_platzhalter(text: str, werte: dict[str, str]) -> str:
    """Ersetzt nur bekannte Platzhalter. Andere geschweifte Klammern bleiben, wie sie sind."""
    for name in PLATZHALTER:
        text = text.replace("{" + name + "}", werte.get(name, ""))
    return text


def pauschale_vorschlagen(stufe: int, kontakt_art: str | None, vorherige: bool | None) -> bool:
    """Ob die Verzugspauschale vorausgewählt ist. `vorherige`: Wahl bei der letzten Mahnung ab
    Stufe 2 (None, wenn es keine gibt). Sonst nur bei Firmen, weil Verbraucher sie nicht
    schulden."""
    if stufe < PAUSCHALE_AB_STUFE:
        return False
    return vorherige if vorherige is not None else kontakt_art == "firma"


@dataclass(frozen=True)
class Stufe:
    nummer: int
    bezeichnung: str
    tage_nach: int  # Abstand zur Fälligkeit (Stufe 1) bzw. zur vorherigen Mahnung
    frist_tage: int  # neue Zahlungsfrist auf dem Schreiben


@dataclass(frozen=True)
class LetzteMahnung:
    stufe: int
    datum: date


def naechste_stufe(stufen: list[Stufe], letzte: LetzteMahnung | None) -> Stufe | None:
    sortiert = sorted(stufen, key=lambda s: s.nummer)
    if letzte is None:
        return sortiert[0] if sortiert else None
    spaeter = [s for s in sortiert if s.nummer > letzte.stufe]
    return spaeter[0] if spaeter else None


def faellige_stufe(
    *,
    faellig_am: date | None,
    letzte: LetzteMahnung | None,
    stufen: list[Stufe],
    heute: date,
) -> Stufe | None:
    if faellig_am is None:
        return None
    stufe = naechste_stufe(stufen, letzte)
    if stufe is None:
        return None
    basis = faellig_am if letzte is None else letzte.datum
    return stufe if heute >= basis + timedelta(days=stufe.tage_nach) else None


def faellig_ab(
    *, faellig_am: date | None, letzte: LetzteMahnung | None, stufe: Stufe
) -> date | None:
    """Ab wann die Stufe laut Zeitplan dran ist. Früher erstellen darf man sie, aber der Kunde
    bekommt dann weniger Zeit als vorgesehen."""
    if faellig_am is None:
        return None
    basis = faellig_am if letzte is None else letzte.datum
    return basis + timedelta(days=stufe.tage_nach)
