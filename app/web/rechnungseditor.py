"""Liest das Formular des Rechnungseditors in Kopf- und Positionsdaten."""

import re
from dataclasses import dataclass, field
from datetime import date

from werkzeug.datastructures import MultiDict

from app.domain.geld import GeldFormatFehler, cent_zu_euro, euro_zu_cent
from app.domain.rechnung import (
    MengenFehler,
    RabattFehler,
    menge_als_text,
    menge_zu_tausendstel,
    rabatt_zu_basispunkten,
)
from app.extensions import db
from app.models import LEISTUNG_ARTEN, Artikel
from app.services.rechnungen import Kopfdaten, Positionsdaten, position_aus_artikel

_POSITION = re.compile(r"^pos-(\d+)-typ$")


@dataclass
class Eingabe:
    kopf: Kopfdaten | None = None
    positionen: list[Positionsdaten] = field(default_factory=list)
    fehler: dict[str, str] = field(default_factory=dict)
    # Rohwerte, damit das Formular bei Fehlern genau so wieder erscheint
    roh: list[dict] = field(default_factory=list)


def _text(formular: MultiDict, name: str) -> str | None:
    wert = (formular.get(name) or "").strip()
    return wert or None


def _datum(formular: MultiDict, name: str, fehler: dict, pflicht: bool = False) -> date | None:
    wert = _text(formular, name)
    if not wert:
        if pflicht:
            fehler[name] = "Pflichtfeld"
        return None
    try:
        return date.fromisoformat(wert)
    except ValueError:
        fehler[name] = "Ungültiges Datum."
        return None


def lies_formular(formular: MultiDict) -> Eingabe:
    eingabe = Eingabe()
    fehler = eingabe.fehler

    leistung_art = formular.get("leistung_art", "leistungsdatum")
    if leistung_art not in LEISTUNG_ARTEN:
        fehler["leistung_art"] = "Bitte aus der Liste wählen."
        leistung_art = "leistungsdatum"

    ziel_text = _text(formular, "zahlungsziel_tage") or "0"
    if not ziel_text.isdigit() or int(ziel_text) > 365:
        fehler["zahlungsziel_tage"] = "Bitte Tage zwischen 0 und 365 angeben."
        ziel_text = "0"

    kontakt_text = _text(formular, "kontakt_id")
    eingabe.kopf = Kopfdaten(
        kontakt_id=int(kontakt_text) if kontakt_text and kontakt_text.isdigit() else None,
        empfaenger_name=_text(formular, "empfaenger_name"),
        empfaenger_zusatz=_text(formular, "empfaenger_zusatz"),
        empfaenger_strasse=_text(formular, "empfaenger_strasse"),
        empfaenger_plz=_text(formular, "empfaenger_plz"),
        empfaenger_ort=_text(formular, "empfaenger_ort"),
        empfaenger_land=_text(formular, "empfaenger_land") or "Deutschland",
        rechnungsdatum=_datum(formular, "rechnungsdatum", fehler, pflicht=True) or date.today(),
        leistung_art=leistung_art,
        leistung_von=_datum(formular, "leistung_von", fehler),
        leistung_bis=(
            _datum(formular, "leistung_bis", fehler)
            if leistung_art == "leistungszeitraum"
            else None
        ),
        titel=(_text(formular, "titel") or "Rechnung")[:100],
        einleitung=_text(formular, "einleitung"),
        nachbemerkung=_text(formular, "nachbemerkung"),
        hinweis_steuerbefreiung=_text(formular, "hinweis_steuerbefreiung"),
        zahlungsziel_tage=int(ziel_text),
        qr_ueberweisung=formular.get("qr_ueberweisung") == "y",
    )

    indizes = sorted(int(m.group(1)) for k in formular if (m := _POSITION.match(k)))
    for i in indizes:
        p = f"pos-{i}-"
        roh = {k[len(p) :]: v for k, v in formular.items() if k.startswith(p)}
        eingabe.roh.append(roh)
        typ = "text" if roh.get("typ") == "text" else "artikel"
        daten = Positionsdaten(
            typ=typ,
            bezeichnung=(roh.get("bezeichnung") or "").strip()[:200],
            beschreibung=(roh.get("beschreibung") or "").strip() or None,
            artikel_id=int(roh["artikel_id"]) if (roh.get("artikel_id") or "").isdigit() else None,
        )
        if typ == "artikel":
            daten.einheit = (roh.get("einheit") or "").strip()[:30] or None
            try:
                daten.menge_tausendstel = menge_zu_tausendstel(roh.get("menge") or "1")
            except MengenFehler as e:
                fehler[f"{p}menge"] = str(e)
            try:
                daten.einzelpreis_cent = euro_zu_cent(roh.get("preis") or "0")
            except GeldFormatFehler:
                fehler[f"{p}preis"] = "Ungültiger Preis, z. B. 65,00."
            try:
                daten.rabatt_bp = rabatt_zu_basispunkten(roh.get("rabatt") or "")
            except RabattFehler as e:
                fehler[f"{p}rabatt"] = str(e)
        eingabe.positionen.append(daten)
    return eingabe


def wende_positionsaktion(
    aktion: str, positionen: list[Positionsdaten], formular: MultiDict
) -> list[Positionsdaten]:
    """Knöpfe unter den Positionen: Artikel, freie Position, Freitext hinzufügen oder entfernen."""
    if aktion == "artikel":
        # Eine leere Position (z. B. die erste im neuen Entwurf) wird durch den Artikel ersetzt.
        positionen = [
            p for p in positionen if p.typ == "text" or p.bezeichnung or p.einzelpreis_cent
        ]
        artikel_id = formular.get("neuer_artikel", "")
        artikel = db.session.get(Artikel, int(artikel_id)) if artikel_id.isdigit() else None
        if artikel:
            positionen.append(position_aus_artikel(artikel))
    elif aktion == "position":
        positionen.append(Positionsdaten(typ="artikel", bezeichnung=""))
    elif aktion == "freitext":
        positionen.append(Positionsdaten(typ="text", bezeichnung=""))
    elif aktion.startswith("entfernen-"):
        index = aktion.removeprefix("entfernen-")
        if index.isdigit() and int(index) < len(positionen):
            positionen.pop(int(index))
    return positionen


def roh_aus_rechnung(rechnung) -> list[dict]:
    """Positionen als Formularwerte für die Anzeige."""
    zeilen = []
    for p in rechnung.positionen:
        zeilen.append(
            {
                "typ": p.typ,
                "bezeichnung": p.bezeichnung,
                "beschreibung": p.beschreibung or "",
                "menge": menge_als_text(p.menge_tausendstel) if p.typ == "artikel" else "",
                "einheit": p.einheit or "",
                "preis": cent_zu_euro(p.einzelpreis_cent)[:-2] if p.typ == "artikel" else "",
                "rabatt": (
                    cent_zu_euro(p.rabatt_bp)[:-2].removesuffix(",00") if p.rabatt_bp else ""
                ),
                "artikel_id": str(p.artikel_id or ""),
                "betrag_cent": p.betrag_cent,
            }
        )
    return zeilen
