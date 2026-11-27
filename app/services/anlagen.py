"""Anlagegüter anlegen und ihre AfA je Jahr berechnen (docs/domain/euer.md)."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select

from app.domain.afa import ARTEN, SOFORT, AfaUngueltig, gwg_grenze_brutto, plan, restbuchwert
from app.extensions import db
from app.models import AfaVorgabe, Anlagegut, Buchung
from app.services.protokoll import protokolliere

GWG_KATEGORIE = "Geringwertige Anschaffungen"
REGELSTEUERSATZ = 19


def gwg_grenze_netto(jahr: int) -> int:
    """Neueste bekannte Grenze bis zu diesem Jahr (frühere Jahre: früheste bekannte)."""
    grenze = db.session.execute(
        select(AfaVorgabe.gwg_netto_cent)
        .where(AfaVorgabe.steuerjahr <= jahr)
        .order_by(AfaVorgabe.steuerjahr.desc())
        .limit(1)
    ).scalar()
    if grenze is None:
        grenze = db.session.execute(
            select(AfaVorgabe.gwg_netto_cent).order_by(AfaVorgabe.steuerjahr).limit(1)
        ).scalar()
    return grenze or 0


def ueber_gwg_grenze(buchung: Buchung) -> bool:
    """Für die Nachfrage nach dem Festschreiben: „Geringwertige Anschaffung“ über der Grenze."""
    if buchung.art != "ausgabe" or not buchung.kategorie or buchung.storno_von_id:
        return False
    if buchung.kategorie.name != GWG_KATEGORIE:
        return False
    grenze = gwg_grenze_netto(buchung.belegdatum.year)
    return buchung.betrag_cent > gwg_grenze_brutto(grenze, REGELSTEUERSATZ)


def abschreibung_sinnvoll(buchung: Buchung) -> bool:
    """Ob sich der Hinweis „Über mehrere Jahre abschreiben“ lohnt: nur über der GWG-Grenze.
    Darunter darf alles sofort als Ausgabe zählen, der Hinweis würde nur verwirren."""
    if buchung.art != "ausgabe" or buchung.storno_von_id:
        return False
    grenze = gwg_grenze_netto(buchung.belegdatum.year)
    return buchung.betrag_cent > gwg_grenze_brutto(grenze, REGELSTEUERSATZ)


def kann_anlagegut_werden(buchung: Buchung) -> str | None:
    """Gibt den Grund zurück, warum nicht, oder None."""
    if buchung.art != "ausgabe":
        return "Nur Ausgaben können Anlagegüter werden."
    if buchung.ist_entwurf:
        return "Bitte die Ausgabe zuerst festschreiben."
    if buchung.storno_von_id or buchung.storniert:
        return "Die Buchung ist storniert."
    if db.session.execute(select(Anlagegut.id).where(Anlagegut.buchung_id == buchung.id)).first():
        return "Zu dieser Buchung gibt es schon ein Anlagegut."
    if buchung.betrieblich_prozent != 100:
        return (
            "Anlagegüter mit privatem Anteil sind noch nicht möglich. Bitte mit deiner "
            "Steuerberatung klären, wie die Anschaffung behandelt wird."
        )
    return None


def lege_an(
    buchung: Buchung,
    *,
    bezeichnung: str,
    art: str,
    anschaffungsdatum: date,
    nutzungsdauer_jahre: int,
    nutzer_id: int,
) -> Anlagegut:
    grund = kann_anlagegut_werden(buchung)
    if grund:
        raise AfaUngueltig(grund)
    if art in SOFORT:
        nutzungsdauer_jahre = 1
    plan(buchung.betrag_cent, anschaffungsdatum, nutzungsdauer_jahre, art)  # prüft die Werte
    anlagegut = Anlagegut(
        buchung_id=buchung.id,
        bezeichnung=(bezeichnung or "").strip()[:200] or "Anschaffung",
        art=art,
        anschaffungsdatum=anschaffungsdatum,
        anschaffungskosten_cent=buchung.betrag_cent,
        nutzungsdauer_jahre=nutzungsdauer_jahre,
        erstellt_von=nutzer_id,
    )
    db.session.add(anlagegut)
    db.session.flush()
    protokolliere(
        "anlagegut_angelegt",
        nutzer_id=nutzer_id,
        objekt_typ="buchung",
        objekt_id=buchung.id,
        details={"anlagegut_id": anlagegut.id, "art": art, "jahre": nutzungsdauer_jahre},
    )
    db.session.commit()
    return anlagegut


def afa_plan(anlagegut: Anlagegut) -> dict[int, int]:
    return plan(
        anlagegut.anschaffungskosten_cent,
        anlagegut.anschaffungsdatum,
        anlagegut.nutzungsdauer_jahre,
        anlagegut.art,
    )


@dataclass(frozen=True)
class Zeile:
    anlagegut: Anlagegut
    afa_cent: int
    restbuchwert_cent: int
    kennzahl: str


def verzeichnis(jahr: int) -> list[Zeile]:
    """Alle aktiven Anlagegüter, die bis Ende des Jahres angeschafft wurden."""
    guter = db.session.execute(
        select(Anlagegut)
        .where(func.extract("year", Anlagegut.anschaffungsdatum) <= jahr)
        .order_by(Anlagegut.anschaffungsdatum, Anlagegut.id)
    ).scalars()
    zeilen = []
    for gut in guter:
        if not gut.aktiv:
            continue
        p = afa_plan(gut)
        rest = restbuchwert(gut.anschaffungskosten_cent, p, jahr)
        afa = p.get(jahr, 0)
        if afa or rest:
            zeilen.append(Zeile(gut, afa, rest, ARTEN[gut.art][1]))
    return zeilen


def buchungen_mit_anlagegut() -> set[int]:
    return set(db.session.execute(select(Anlagegut.buchung_id)).scalars())


def ohne_anlagegut() -> list[Buchung]:
    """Festgeschriebene „Geringwertige Anschaffungen“ über der Grenze ohne Anlagegut. Sie
    stehen sonst voll als Ausgabe in der EÜR (docs/domain/euer.md)."""
    storniert = select(Buchung.storno_von_id).where(Buchung.storno_von_id.is_not(None))
    mit_anlage = select(Anlagegut.buchung_id)
    kandidaten = db.session.execute(
        select(Buchung)
        .where(
            Buchung.art == "ausgabe",
            Buchung.status == "festgeschrieben",
            Buchung.storno_von_id.is_(None),
            Buchung.id.not_in(storniert),
            Buchung.id.not_in(mit_anlage),
        )
        .order_by(Buchung.belegdatum)
    ).scalars()
    return [b for b in kandidaten if ueber_gwg_grenze(b)]


def korrigiere(buchung: Buchung, nutzer_id: int) -> Buchung:
    """Falsches Anlagegut (Art, Dauer, Datum) korrigieren, ohne etwas zu überschreiben:
    Die Ausgabe wird storniert (das hebt das Anlagegut auf) und mit denselben Angaben und
    Zahlungen neu gebucht. Zur neuen Buchung legt man das Anlagegut dann richtig an."""
    from app.services.buchungen import (
        Buchungsdaten,
        erfasse_zahlung,
        festschreiben,
        lege_entwurf_an,
        storniere,
    )

    gut = buchung.anlagegut
    if gut is None or not gut.aktiv:
        raise AfaUngueltig("Zu dieser Buchung gibt es kein gültiges Anlagegut.")
    zahlungen = [
        z
        for z in buchung.zahlungen
        if z.storno_von_id is None and not any(g.storno_von_id == z.id for g in buchung.zahlungen)
    ]
    storniere(buchung, nutzer_id)
    neu = lege_entwurf_an(
        Buchungsdaten(
            art=buchung.art,
            belegdatum=buchung.belegdatum,
            betrag_cent=buchung.betrag_cent,
            kategorie_id=buchung.kategorie_id,
            betrieblich_prozent=buchung.betrieblich_prozent,
            kontakt_id=buchung.kontakt_id,
            partner=buchung.partner,
            belegnummer=buchung.belegnummer,
            beschreibung=buchung.beschreibung,
            beleg_id=buchung.beleg_id,
        ),
        nutzer_id,
    )
    festschreiben(neu, nutzer_id)
    for z in zahlungen:
        erfasse_zahlung(
            neu,
            datum=z.datum,
            betrag_cent=z.betrag_cent,
            zahlungsart=z.zahlungsart,
            notiz=z.notiz,
            nutzer_id=nutzer_id,
        )
    protokolliere(
        "anlagegut_korrigiert",
        nutzer_id=nutzer_id,
        objekt_typ="buchung",
        objekt_id=neu.id,
        details={"alte_buchung": buchung.id, "altes_anlagegut": gut.id},
    )
    db.session.commit()
    return neu
