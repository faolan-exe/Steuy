"""Wann ist welche Mahnstufe fällig? (docs/domain/mahnwesen.md)"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

# Verzugspauschale nach § 288 Abs. 5 BGB, nur gegenüber Schuldnern, die keine Verbraucher sind
VERZUGSPAUSCHALE_CENT = 4000
PAUSCHALE_AB_STUFE = 2
TEXT_MAX = 3000

# Vorgefertigte Brieftexte je Stufe. Dieselben Texte setzt die Migration als Startwert.
# {pauschale} wird zum Satz über die Verzugspauschale oder bleibt leer, wenn sie nicht dabei ist.
STANDARDTEXTE = {
    1: (
        "Guten Tag,\n\n"
        "sicher ist es Ihnen im Alltag nur entgangen: Für die Rechnung {nummer} vom "
        "{rechnungsdatum} ist noch ein Betrag von {betrag} offen. Sie war am {faellig} "
        "fällig.\n\n"
        "Bitte überweisen Sie den offenen Betrag bis zum {frist}.\n\n"
        "Bitte beachten Sie: Geht die Zahlung bis dahin nicht ein, muss ich Ihnen mit der "
        "nächsten Mahnung Verzugskosten in Rechnung stellen, also die gesetzliche "
        "Verzugspauschale von 40,00 € und Verzugszinsen."
    ),
    2: (
        "Guten Tag,\n\n"
        "trotz meiner Zahlungserinnerung ist die Rechnung {nummer} vom {rechnungsdatum} noch "
        "offen. Sie war am {faellig} fällig, Sie befinden sich damit in Zahlungsverzug.\n\n"
        "{pauschale}\n\n"
        "Bitte überweisen Sie den Gesamtbetrag von {gesamt} bis spätestens {frist}. Geht bis "
        "dahin keine Zahlung ein, entstehen Ihnen weitere Kosten: Ich berechne Verzugszinsen "
        "und mahne erneut."
    ),
    3: (
        "Guten Tag,\n\n"
        "trotz Zahlungserinnerung und Mahnung habe ich zur Rechnung {nummer} vom "
        "{rechnungsdatum} noch keine vollständige Zahlung erhalten. Dies ist meine letzte "
        "Mahnung.\n\n"
        "{pauschale}\n\n"
        "Bitte überweisen Sie den Gesamtbetrag von {gesamt} bis spätestens {frist}. Geht das "
        "Geld bis dahin nicht ein, leite ich ohne weitere Ankündigung ein gerichtliches "
        "Mahnverfahren ein. Die Kosten dafür und die Verzugszinsen gehen zu Ihren Lasten.\n\n"
        "Gibt es einen Grund, warum Sie noch nicht zahlen konnten, melden Sie sich bitte "
        "vorher bei mir."
    ),
}

PAUSCHALE_SATZ = (
    "Da Sie sich in Zahlungsverzug befinden, berechne ich Ihnen zusätzlich die gesetzliche "
    "Verzugspauschale von 40,00 € (§ 288 Abs. 5 BGB)."
)

PLATZHALTER = {
    "nummer": "Rechnungsnummer",
    "rechnungsdatum": "Rechnungsdatum",
    "faellig": "Fälligkeit der Rechnung",
    "frist": "neue Zahlungsfrist",
    "betrag": "offener Rechnungsbetrag",
    "gesamt": "zu zahlender Betrag mit Verzugspauschale",
    "pauschale": "Satz zur Verzugspauschale (leer, wenn sie nicht dabei ist)",
}


def fuelle_platzhalter(text: str, werte: dict[str, str]) -> str:
    """Ersetzt nur bekannte Platzhalter. Andere geschweifte Klammern bleiben, wie sie sind."""
    for name in PLATZHALTER:
        text = text.replace("{" + name + "}", werte.get(name, ""))
    # Ein leerer Platzhalter in eigener Zeile soll keine Lücke im Brief hinterlassen
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def pauschale_vorschlagen(stufe: int, vorherige: bool | None) -> bool:
    """Ob die Verzugspauschale vorausgewählt ist: ab Stufe 2 immer, außer sie wurde bei der
    vorherigen Mahnung (ab Stufe 2) abgewählt. `vorherige` ist dann deren Wahl."""
    if stufe < PAUSCHALE_AB_STUFE:
        return False
    return True if vorherige is None else vorherige


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
