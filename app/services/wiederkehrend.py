"""Wiederkehrende Rechnungen: Vorlagen verwalten und fällige Rechnungen erzeugen.

Ein Lauf (Zeitplan-Dienst oder Knopf) legt für jeden erreichten Termin einen Rechnungsentwurf an.
Je nach Einstellung wird er auch festgeschrieben und per E-Mail verschickt. Der nächste Termin
wird immer **vor** dem Festschreiben weitergesetzt: Stürzt etwas ab, bleibt höchstens ein Entwurf
übrig, aber keine doppelte Rechnung.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select, text

from app.domain.rechnung import Position, positionsbetrag, summe
from app.domain.wiederkehrend import (
    INTERVALLE,
    VERSAND_ARTEN,
    ersetze_platzhalter,
    faellige_termine,
    naechster_termin,
    zeitraum,
)
from app.extensions import db
from app.models import Nutzer, Rechnung, WiederkehrendePosition, WiederkehrendeRechnung
from app.services import mail, versand
from app.services.einrichtung import aktuelles_gewerbe
from app.services.mail import MailFehler
from app.services.protokoll import protokolliere
from app.services.rechnungen import (
    Kopfdaten,
    NichtFinalisierbar,
    Positionsdaten,
    finalisiere,
    neuer_entwurf,
    speichere_entwurf,
)

SPERRE_SCHLUESSEL = 734_002


class VorlageUngueltig(ValueError):
    pass


@dataclass
class Einstellungen:
    name: str
    intervall: str
    naechste_am: date
    ende_am: date | None
    versand: str
    aktiv: bool


@dataclass
class Lauf:
    erstellt: list[str] = field(default_factory=list)
    festgeschrieben: list[str] = field(default_factory=list)
    versendet: list[str] = field(default_factory=list)
    probleme: list[tuple[str, str]] = field(default_factory=list)

    @property
    def leer(self) -> bool:
        return not (self.erstellt or self.probleme)

    def text(self) -> str:
        if self.leer:
            return "Keine Rechnung fällig."
        teile = [f"{len(self.erstellt)} Rechnung(en) angelegt"]
        if self.festgeschrieben:
            teile.append(f"{len(self.festgeschrieben)} festgeschrieben")
        if self.versendet:
            teile.append(f"{len(self.versendet)} verschickt")
        if self.probleme:
            teile.append(f"{len(self.probleme)} mit Hinweis")
        return ", ".join(teile) + "."


def pruefe_einstellungen(e: Einstellungen) -> None:
    if not e.name.strip():
        raise VorlageUngueltig("Bitte einen Namen eintragen.")
    if e.intervall not in INTERVALLE:
        raise VorlageUngueltig("Bitte ein Intervall wählen.")
    if e.versand not in VERSAND_ARTEN:
        raise VorlageUngueltig("Bitte wählen, was bei einem Termin passieren soll.")
    if e.ende_am is not None and e.ende_am < e.naechste_am:
        raise VorlageUngueltig("Das Ende liegt vor dem ersten Termin.")


def _positionen_uebernehmen(vorlage: WiederkehrendeRechnung, positionen: list[Positionsdaten]):
    vorlage.positionen.clear()
    db.session.flush()
    for nr, p in enumerate(positionen, start=1):
        vorlage.positionen.append(
            WiederkehrendePosition(
                position=nr,
                typ=p.typ,
                artikel_id=p.artikel_id,
                bezeichnung=p.bezeichnung,
                beschreibung=p.beschreibung,
                menge_tausendstel=p.menge_tausendstel if p.typ == "artikel" else 0,
                einheit=p.einheit if p.typ == "artikel" else None,
                einzelpreis_cent=p.einzelpreis_cent if p.typ == "artikel" else 0,
                rabatt_bp=p.rabatt_bp if p.typ == "artikel" else 0,
                betrag_cent=(
                    positionsbetrag(p.einzelpreis_cent, p.menge_tausendstel, p.rabatt_bp)
                    if p.typ == "artikel"
                    else 0
                ),
            )
        )
    vorlage.summe_cent = summe(
        [
            Position(p.typ, p.einzelpreis_cent, p.menge_tausendstel, p.rabatt_bp)
            for p in vorlage.positionen
        ]
    )


def lege_leer_an(nutzer_id: int, heute: date | None = None) -> WiederkehrendeRechnung:
    heute = heute or date.today()
    gewerbe = aktuelles_gewerbe()
    vorlage = WiederkehrendeRechnung(
        name="Neue wiederkehrende Rechnung",
        titel="Rechnung",
        einleitung=gewerbe.rechnung_einleitung,
        nachbemerkung=gewerbe.rechnung_nachbemerkung,
        hinweis_steuerbefreiung=gewerbe.hinweis_steuerbefreiung,
        zahlungsziel_tage=gewerbe.zahlungsziel_tage,
        qr_ueberweisung=bool(gewerbe.iban),
        naechste_am=heute,
        anker_tag=heute.day,
        erstellt_von=nutzer_id,
        empfaenger_land="Deutschland",
    )
    vorlage.positionen.append(WiederkehrendePosition(position=1, typ="artikel", bezeichnung=""))
    db.session.add(vorlage)
    db.session.flush()
    protokolliere(
        "wiederkehrend_angelegt",
        nutzer_id=nutzer_id,
        objekt_typ="wiederkehrende_rechnung",
        objekt_id=vorlage.id,
    )
    db.session.commit()
    return vorlage


def lege_aus_rechnung_an(rechnung: Rechnung, nutzer_id: int) -> WiederkehrendeRechnung:
    """Neue Vorlage mit Kunde, Texten und Positionen einer vorhandenen Rechnung."""
    if not rechnung.ist_rechnung:
        raise VorlageUngueltig("Nur aus Rechnungen kann eine wiederkehrende Rechnung entstehen.")
    start = naechster_termin(rechnung.rechnungsdatum, "monatlich", rechnung.rechnungsdatum.day)
    vorlage = WiederkehrendeRechnung(
        name=" ".join(filter(None, [rechnung.empfaenger_name, rechnung.titel]))[:200],
        kontakt_id=rechnung.kontakt_id,
        empfaenger_name=rechnung.empfaenger_name,
        empfaenger_zusatz=rechnung.empfaenger_zusatz,
        empfaenger_strasse=rechnung.empfaenger_strasse,
        empfaenger_plz=rechnung.empfaenger_plz,
        empfaenger_ort=rechnung.empfaenger_ort,
        empfaenger_land=rechnung.empfaenger_land,
        titel=rechnung.titel,
        einleitung=rechnung.einleitung,
        nachbemerkung=rechnung.nachbemerkung,
        hinweis_steuerbefreiung=rechnung.hinweis_steuerbefreiung,
        zahlungsziel_tage=rechnung.zahlungsziel_tage,
        qr_ueberweisung=rechnung.qr_ueberweisung,
        naechste_am=start,
        anker_tag=rechnung.rechnungsdatum.day,
        erstellt_von=nutzer_id,
    )
    db.session.add(vorlage)
    db.session.flush()
    for p in rechnung.positionen:
        vorlage.positionen.append(
            WiederkehrendePosition(
                position=p.position,
                typ=p.typ,
                artikel_id=p.artikel_id,
                bezeichnung=p.bezeichnung,
                beschreibung=p.beschreibung,
                menge_tausendstel=p.menge_tausendstel,
                einheit=p.einheit,
                einzelpreis_cent=p.einzelpreis_cent,
                rabatt_bp=p.rabatt_bp,
                betrag_cent=p.betrag_cent,
            )
        )
    vorlage.summe_cent = rechnung.summe_cent
    protokolliere(
        "wiederkehrend_angelegt",
        nutzer_id=nutzer_id,
        objekt_typ="wiederkehrende_rechnung",
        objekt_id=vorlage.id,
        details={"aus_rechnung": rechnung.nummer},
    )
    db.session.commit()
    return vorlage


def speichere(
    vorlage: WiederkehrendeRechnung,
    kopf: Kopfdaten,
    positionen: list[Positionsdaten],
    einstellungen: Einstellungen,
    nutzer_id: int,
) -> None:
    pruefe_einstellungen(einstellungen)
    if kopf.kontakt_id and kopf.kontakt_id != vorlage.kontakt_id:
        from app.models import Kontakt
        from app.services.rechnungen import empfaenger_aus_kontakt

        kontakt = db.session.get(Kontakt, kopf.kontakt_id)
        if kontakt:
            for feld, wert in empfaenger_aus_kontakt(kontakt).items():
                setattr(kopf, feld, wert)
    for feld in (
        "kontakt_id",
        "empfaenger_name",
        "empfaenger_zusatz",
        "empfaenger_strasse",
        "empfaenger_plz",
        "empfaenger_ort",
        "empfaenger_land",
        "titel",
        "einleitung",
        "nachbemerkung",
        "hinweis_steuerbefreiung",
        "zahlungsziel_tage",
        "qr_ueberweisung",
    ):
        setattr(vorlage, feld, getattr(kopf, feld))
    vorlage.name = einstellungen.name.strip()[:200]
    vorlage.intervall = einstellungen.intervall
    if einstellungen.naechste_am != vorlage.naechste_am:
        # Ein neuer Starttermin legt auch den Ankertag fest (z. B. immer am 15.)
        vorlage.anker_tag = einstellungen.naechste_am.day
    vorlage.naechste_am = einstellungen.naechste_am
    vorlage.ende_am = einstellungen.ende_am
    vorlage.versand = einstellungen.versand
    vorlage.aktiv = einstellungen.aktiv
    _positionen_uebernehmen(vorlage, positionen)
    protokolliere(
        "wiederkehrend_geaendert",
        nutzer_id=nutzer_id,
        objekt_typ="wiederkehrende_rechnung",
        objekt_id=vorlage.id,
    )
    db.session.commit()


def setze_aktiv(vorlage: WiederkehrendeRechnung, aktiv: bool, nutzer_id: int) -> None:
    vorlage.aktiv = aktiv
    protokolliere(
        "wiederkehrend_fortgesetzt" if aktiv else "wiederkehrend_pausiert",
        nutzer_id=nutzer_id,
        objekt_typ="wiederkehrende_rechnung",
        objekt_id=vorlage.id,
    )
    db.session.commit()


def loesche(vorlage: WiederkehrendeRechnung, nutzer_id: int) -> None:
    """Nur Vorlagen ohne erzeugte Rechnungen. Sonst bleibt sie (pausiert) bestehen."""
    if vorlage.erzeugt_anzahl or _hat_rechnungen(vorlage):
        raise VorlageUngueltig(
            "Aus dieser Vorlage sind schon Rechnungen entstanden. Sie lässt sich nur pausieren."
        )
    protokolliere(
        "wiederkehrend_geloescht",
        nutzer_id=nutzer_id,
        objekt_typ="wiederkehrende_rechnung",
        objekt_id=vorlage.id,
        details={"name": vorlage.name},
    )
    db.session.delete(vorlage)
    db.session.commit()


def _hat_rechnungen(vorlage: WiederkehrendeRechnung) -> bool:
    return (
        db.session.execute(
            select(Rechnung.id).where(Rechnung.wiederkehrend_id == vorlage.id).limit(1)
        ).first()
        is not None
    )


def rechnungen_der_vorlage(vorlage: WiederkehrendeRechnung) -> list[Rechnung]:
    return list(
        db.session.execute(
            select(Rechnung)
            .where(Rechnung.wiederkehrend_id == vorlage.id)
            .order_by(Rechnung.rechnungsdatum.desc(), Rechnung.id.desc())
        ).scalars()
    )


def alle() -> list[WiederkehrendeRechnung]:
    return list(
        db.session.execute(
            select(WiederkehrendeRechnung).order_by(
                WiederkehrendeRechnung.aktiv.desc(), WiederkehrendeRechnung.naechste_am
            )
        ).scalars()
    )


def _erzeuge(
    vorlage: WiederkehrendeRechnung, termin: date, nutzer_id: int, heute: date
) -> Rechnung:
    """Rechnungsentwurf für den Abrechnungszeitraum ab `termin` anlegen und Termin weitersetzen."""
    von, bis = zeitraum(termin, vorlage.intervall, vorlage.anker_tag)

    def text_(wert: str | None) -> str | None:
        return ersetze_platzhalter(wert, von, bis)

    rechnung = neuer_entwurf(nutzer_id, "rechnung", kontakt=vorlage.kontakt)
    kopf = Kopfdaten(
        kontakt_id=vorlage.kontakt_id,
        empfaenger_name=vorlage.empfaenger_name,
        empfaenger_zusatz=vorlage.empfaenger_zusatz,
        empfaenger_strasse=vorlage.empfaenger_strasse,
        empfaenger_plz=vorlage.empfaenger_plz,
        empfaenger_ort=vorlage.empfaenger_ort,
        empfaenger_land=vorlage.empfaenger_land,
        rechnungsdatum=heute,
        leistung_art="leistungszeitraum",
        leistung_von=von,
        leistung_bis=bis,
        titel=(text_(vorlage.titel) or "Rechnung")[:100],
        einleitung=text_(vorlage.einleitung),
        nachbemerkung=text_(vorlage.nachbemerkung),
        hinweis_steuerbefreiung=vorlage.hinweis_steuerbefreiung,
        zahlungsziel_tage=vorlage.zahlungsziel_tage,
        qr_ueberweisung=vorlage.qr_ueberweisung,
    )
    positionen = [
        Positionsdaten(
            typ=p.typ,
            bezeichnung=(text_(p.bezeichnung) or "")[:200],
            beschreibung=text_(p.beschreibung),
            menge_tausendstel=p.menge_tausendstel or 1000,
            einheit=p.einheit,
            einzelpreis_cent=p.einzelpreis_cent,
            rabatt_bp=p.rabatt_bp,
            artikel_id=p.artikel_id,
        )
        for p in vorlage.positionen
    ]
    speichere_entwurf(rechnung, kopf, positionen)
    rechnung.wiederkehrend_id = vorlage.id
    vorlage.naechste_am = naechster_termin(termin, vorlage.intervall, vorlage.anker_tag)
    vorlage.erzeugt_anzahl += 1
    protokolliere(
        "wiederkehrend_rechnung_erzeugt",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={"vorlage_id": vorlage.id, "zeitraum": f"{von.isoformat()}/{bis.isoformat()}"},
    )
    db.session.commit()
    return rechnung


def _nachbearbeiten(
    vorlage: WiederkehrendeRechnung, rechnung: Rechnung, nutzer_id: int, ergebnis: Lauf
) -> str | None:
    """Festschreiben und Verschicken je nach Einstellung. Gibt einen Hinweis zurück, falls nötig."""
    if vorlage.versand == "entwurf":
        return None
    try:
        finalisiere(rechnung, nutzer_id)
    except NichtFinalisierbar as fehler:
        db.session.rollback()
        return "Als Entwurf liegen geblieben, weil Angaben fehlen: " + "; ".join(fehler.fehler)
    ergebnis.festgeschrieben.append(rechnung.nummer)
    if vorlage.versand != "senden":
        return None
    vorschlag = versand.vorschlag(rechnung)
    if not mail.eingerichtet():
        return f"{rechnung.nummer} nicht verschickt: E-Mail-Versand ist nicht eingerichtet."
    if not vorschlag["an"]:
        return f"{rechnung.nummer} nicht verschickt: Beim Kunden fehlt die E-Mail-Adresse."
    try:
        versand.sende_beleg(
            rechnung,
            an=vorschlag["an"],
            betreff=vorschlag["betreff"],
            text=vorschlag["text"],
            nutzer_id=nutzer_id,
        )
    except MailFehler as fehler:
        return f"{rechnung.nummer} nicht verschickt: {fehler}"
    ergebnis.versendet.append(rechnung.nummer)
    return None


def _admin_id() -> int | None:
    kandidaten = db.session.execute(
        select(Nutzer).where(Nutzer.rolle == "admin", Nutzer.aktiv).order_by(Nutzer.id)
    ).scalars()
    return next((n.id for n in kandidaten if n.is_active), None)


def _bearbeite(
    vorlage: WiederkehrendeRechnung, termine: list[date], nutzer_id: int, heute: date, lauf: Lauf
) -> None:
    meldungen: list[str] = []
    for termin in termine:
        rechnung = _erzeuge(vorlage, termin, nutzer_id, heute)
        lauf.erstellt.append(f"{vorlage.name} ({termin:%d.%m.%Y})")
        hinweis = _nachbearbeiten(vorlage, rechnung, nutzer_id, lauf)
        if hinweis:
            meldungen.append(hinweis)
            lauf.probleme.append((vorlage.name, hinweis))
    vorlage.letzter_lauf_am = db.func.now()
    vorlage.letzte_meldung = " ".join(meldungen) or None
    db.session.commit()


def fuehre_aus(nutzer_id: int | None = None, heute: date | None = None) -> Lauf:
    """Alle fälligen Rechnungen erzeugen (Zeitplan-Dienst)."""
    heute = heute or date.today()
    lauf = Lauf()
    nutzer_id = nutzer_id or _admin_id()
    if nutzer_id is None:
        return lauf
    gesperrt = db.session.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": SPERRE_SCHLUESSEL}
    ).scalar()
    if not gesperrt:
        return lauf
    try:
        ids = db.session.execute(
            select(WiederkehrendeRechnung.id).where(
                WiederkehrendeRechnung.aktiv, WiederkehrendeRechnung.naechste_am <= heute
            )
        ).scalars()
        for vorlage_id in list(ids):
            vorlage = db.session.execute(
                select(WiederkehrendeRechnung)
                .where(WiederkehrendeRechnung.id == vorlage_id)
                .with_for_update()
            ).scalar_one()
            termine = faellige_termine(
                vorlage.naechste_am, heute, vorlage.intervall, vorlage.anker_tag, vorlage.ende_am
            )
            if termine:
                _bearbeite(vorlage, termine, nutzer_id, heute, lauf)
            else:
                db.session.rollback()
    finally:
        db.session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SPERRE_SCHLUESSEL})
        db.session.commit()
    return lauf


def erzeuge_jetzt(
    vorlage: WiederkehrendeRechnung, nutzer_id: int, heute: date | None = None
) -> tuple[Rechnung, str | None]:
    """Die nächste Rechnung sofort anlegen (immer als Entwurf), unabhängig vom Termin."""
    heute = heute or date.today()
    if vorlage.beendet:
        raise VorlageUngueltig("Das Ende der Vorlage ist erreicht.")
    rechnung = _erzeuge(vorlage, vorlage.naechste_am, nutzer_id, heute)
    vorlage.letzter_lauf_am = db.func.now()
    vorlage.letzte_meldung = None
    db.session.commit()
    return rechnung, None
