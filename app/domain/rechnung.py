"""Rechenregeln und Pflichtangaben für Rechnungen. Alle Beträge in Cent (ADR 0001).

Mengen werden in Tausendsteln gespeichert (1,5 Stunden = 1500), Rabatte in Basispunkten
(10 % = 1000). So bleibt alles ganzzahlig.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.geld import GeldFormatFehler, euro_zu_cent

_TAUSENDER = re.compile(r"^\d{1,3}(\.\d{3})+$")


class MengenFehler(ValueError):
    pass


class RabattFehler(ValueError):
    pass


def menge_zu_tausendstel(text: str) -> int:
    """„1,5“ → 1500. Höchstens drei Nachkommastellen, größer als null."""
    roh = (text or "").strip()
    if _TAUSENDER.match(roh):
        roh = roh.replace(".", "")
    elif "," in roh:
        if "." in roh:
            vorne, _, hinten = roh.rpartition(",")
            if not _TAUSENDER.match(vorne):
                raise MengenFehler("Ungültige Menge.")
            roh = vorne.replace(".", "") + "," + hinten
        roh = roh.replace(",", ".")

    teile = roh.split(".")
    if (
        len(teile) > 2
        or not teile[0].isdigit()
        or (len(teile) == 2 and (not teile[1].isdigit() or len(teile[1]) > 3))
    ):
        raise MengenFehler("Ungültige Menge, z. B. 1 oder 1,5.")
    tausendstel = int(teile[0]) * 1000 + (int(teile[1].ljust(3, "0")) if len(teile) == 2 else 0)
    if tausendstel <= 0:
        raise MengenFehler("Die Menge muss größer als null sein.")
    return tausendstel


def menge_als_text(tausendstel: int) -> str:
    ganz, rest = divmod(tausendstel, 1000)
    text = f"{ganz:,}".replace(",", ".")
    if rest:
        text += "," + f"{rest:03d}".rstrip("0")
    return text


def rabatt_zu_basispunkten(text: str) -> int:
    """„12,5“ → 1250. Leer bedeutet kein Rabatt. Zwischen 0 und 100 %."""
    if not (text or "").strip():
        return 0
    try:
        bp = euro_zu_cent(text.replace("%", ""))
    except GeldFormatFehler as fehler:
        raise RabattFehler("Ungültiger Rabatt, z. B. 10 oder 12,5.") from fehler
    if not 0 <= bp <= 10000:
        raise RabattFehler("Der Rabatt muss zwischen 0 und 100 % liegen.")
    return bp


def _kaufmaennisch(zaehler: int, nenner: int) -> int:
    """Ganzzahlige Division, halbe Cent werden vom Nullpunkt weg gerundet."""
    vorzeichen = -1 if zaehler < 0 else 1
    ganz, rest = divmod(abs(zaehler), nenner)
    if 2 * rest >= nenner:
        ganz += 1
    return vorzeichen * ganz


def positionsbetrag(einzelpreis_cent: int, menge_tausendstel: int, rabatt_bp: int) -> int:
    return _kaufmaennisch(einzelpreis_cent * menge_tausendstel * (10000 - rabatt_bp), 1000 * 10000)


@dataclass(frozen=True)
class Position:
    typ: str  # "artikel" oder "text"
    einzelpreis_cent: int
    menge_tausendstel: int
    rabatt_bp: int

    @property
    def betrag_cent(self) -> int:
        if self.typ == "text":
            return 0
        return positionsbetrag(self.einzelpreis_cent, self.menge_tausendstel, self.rabatt_bp)


def summe(positionen: list[Position]) -> int:
    return sum(p.betrag_cent for p in positionen)


def formatiere_nummer(praefix: str, nummer: int, stellen: int) -> str:
    return f"{praefix}{nummer:0{stellen}d}"


def faellig_am(rechnungsdatum: date, zahlungsziel_tage: int) -> date:
    return rechnungsdatum + timedelta(days=zahlungsziel_tage)


def fehlende_pflichtangaben(
    *,
    absender_name: str | None,
    absender_anschrift: str | None,
    empfaenger_name: str | None,
    empfaenger_anschrift: str | None,
    rechnungsdatum: date | None,
    leistung_von: date | None,
    hinweis_steuerbefreiung: str | None,
    positionen_mit_betrag: int,
) -> list[str]:
    """Angaben nach § 34a UStDV (Rechnungen von Kleinunternehmern), siehe docs/domain/euer.md."""
    fehlend = []
    if not absender_name or not absender_anschrift:
        fehlend.append("Deine Anschrift fehlt in den Firmendaten.")
    if not empfaenger_name:
        fehlend.append("Empfänger fehlt.")
    if not empfaenger_anschrift:
        fehlend.append("Anschrift des Empfängers fehlt.")
    if not rechnungsdatum:
        fehlend.append("Rechnungsdatum fehlt.")
    if not leistung_von:
        fehlend.append("Liefer- oder Leistungsdatum fehlt.")
    if not hinweis_steuerbefreiung:
        fehlend.append("Hinweis auf die Steuerbefreiung fehlt.")
    elif "19" not in hinweis_steuerbefreiung:
        fehlend.append("Der Hinweis auf die Steuerbefreiung muss § 19 UStG nennen.")
    if positionen_mit_betrag < 1:
        fehlend.append("Die Rechnung braucht mindestens eine Position mit Menge und Preis.")
    return fehlend
