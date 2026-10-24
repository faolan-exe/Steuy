"""Rechnungen: Entwurf bearbeiten, finalisieren, PDF ablegen."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.domain.iban import IbanFehler, pruefe_iban
from app.domain.rechnung import (
    Position,
    faellig_am,
    fehlende_pflichtangaben,
    formatiere_nummer,
    positionsbetrag,
    summe,
)
from app.extensions import db
from app.models import (
    BELEGARTEN,
    Artikel,
    Gewerbe,
    Kontakt,
    Nummernkreis,
    Rechnung,
    Rechnungsposition,
)
from app.services import ablage
from app.services.einrichtung import aktuelles_gewerbe
from app.services.protokoll import protokolliere


class NichtBearbeitbar(RuntimeError):
    pass


class NichtFinalisierbar(ValueError):
    def __init__(self, fehler: list[str]):
        super().__init__("; ".join(fehler))
        self.fehler = fehler


@dataclass
class Kopfdaten:
    kontakt_id: int | None
    empfaenger_name: str | None
    empfaenger_zusatz: str | None
    empfaenger_strasse: str | None
    empfaenger_plz: str | None
    empfaenger_ort: str | None
    empfaenger_land: str | None
    rechnungsdatum: date
    leistung_art: str
    leistung_von: date | None
    leistung_bis: date | None
    titel: str
    einleitung: str | None
    nachbemerkung: str | None
    hinweis_steuerbefreiung: str | None
    zahlungsziel_tage: int
    qr_ueberweisung: bool


@dataclass
class Positionsdaten:
    typ: str
    bezeichnung: str
    beschreibung: str | None = None
    menge_tausendstel: int = 1000
    einheit: str | None = None
    einzelpreis_cent: int = 0
    rabatt_bp: int = 0
    artikel_id: int | None = None
    extra: dict = field(default_factory=dict)


def _pruefe_entwurf(rechnung: Rechnung) -> None:
    if not rechnung.ist_entwurf:
        raise NichtBearbeitbar("Finalisierte Rechnungen können nicht mehr geändert werden.")


def neuer_entwurf(
    nutzer_id: int,
    belegart: str = "rechnung",
    bezug_id: int | None = None,
    kontakt: Kontakt | None = None,
) -> Rechnung:
    gewerbe = aktuelles_gewerbe()
    ist_rechnung = belegart == "rechnung"
    rechnung = Rechnung(
        belegart=belegart,
        bezug_id=bezug_id,
        rechnungsdatum=date.today(),
        leistung_art="leistungsdatum",
        leistung_von=date.today(),
        titel=BELEGARTEN[belegart],
        einleitung=gewerbe.rechnung_einleitung if ist_rechnung else None,
        nachbemerkung=gewerbe.rechnung_nachbemerkung,
        hinweis_steuerbefreiung=gewerbe.hinweis_steuerbefreiung,
        zahlungsziel_tage=gewerbe.zahlungsziel_tage,
        qr_ueberweisung=ist_rechnung and bool(gewerbe.iban),
    )
    if kontakt is not None:
        rechnung.kontakt_id = kontakt.id
        for feld, wert in empfaenger_aus_kontakt(kontakt).items():
            setattr(rechnung, feld, wert)
    rechnung.positionen.append(Rechnungsposition(position=1, typ="artikel", bezeichnung=""))
    db.session.add(rechnung)
    db.session.flush()
    protokolliere(
        "rechnung_entwurf", nutzer_id=nutzer_id, objekt_typ="rechnung", objekt_id=rechnung.id
    )
    db.session.commit()
    return rechnung


def empfaenger_aus_kontakt(kontakt: Kontakt) -> dict:
    return {
        "empfaenger_name": kontakt.name,
        "empfaenger_zusatz": kontakt.adresszusatz,
        "empfaenger_strasse": kontakt.strasse,
        "empfaenger_plz": kontakt.plz,
        "empfaenger_ort": kontakt.ort,
        "empfaenger_land": kontakt.land,
    }


def speichere_entwurf(
    rechnung: Rechnung, kopf: Kopfdaten, positionen: list[Positionsdaten]
) -> None:
    """Ersetzt Kopf und Positionen eines Entwurfs und berechnet die Beträge neu."""
    _pruefe_entwurf(rechnung)
    daten = vars(kopf).copy()
    # Neuer Kunde gewählt: Anschrift aus dem Kontakt übernehmen (Momentaufnahme).
    if kopf.kontakt_id and kopf.kontakt_id != rechnung.kontakt_id:
        kontakt = db.session.get(Kontakt, kopf.kontakt_id)
        if kontakt:
            daten.update(empfaenger_aus_kontakt(kontakt))
    for feld, wert in daten.items():
        setattr(rechnung, feld, wert)

    rechnung.positionen.clear()
    db.session.flush()
    for nr, p in enumerate(positionen, start=1):
        rechnung.positionen.append(
            Rechnungsposition(
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
    rechnung.summe_cent = summe(
        [
            Position(p.typ, p.einzelpreis_cent, p.menge_tausendstel, p.rabatt_bp)
            for p in rechnung.positionen
        ]
    )
    db.session.commit()


def position_aus_artikel(artikel: Artikel) -> Positionsdaten:
    return Positionsdaten(
        typ="artikel",
        bezeichnung=artikel.bezeichnung,
        beschreibung=artikel.beschreibung,
        einheit=artikel.einheit,
        einzelpreis_cent=artikel.preis_cent,
        artikel_id=artikel.id,
    )


def loesche_entwurf(rechnung: Rechnung, nutzer_id: int) -> None:
    _pruefe_entwurf(rechnung)
    protokolliere(
        "rechnung_entwurf_geloescht",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
    )
    db.session.delete(rechnung)
    db.session.commit()


def absender_daten(gewerbe: Gewerbe) -> dict:
    return {
        feld: getattr(gewerbe, feld)
        for feld in (*Gewerbe.FELDER, "kontoinhaber", "iban", "bic", "bank")
    }


def finalisierungsfehler(rechnung: Rechnung, gewerbe: Gewerbe) -> list[str]:
    anschrift_empfaenger = rechnung.empfaenger_strasse and rechnung.empfaenger_ort
    anschrift_absender = gewerbe.strasse and gewerbe.plz and gewerbe.ort
    fehler = fehlende_pflichtangaben(
        absender_name=gewerbe.name,
        absender_anschrift=anschrift_absender and f"{gewerbe.strasse}, {gewerbe.plz} {gewerbe.ort}",
        empfaenger_name=rechnung.empfaenger_name,
        empfaenger_anschrift=anschrift_empfaenger
        and f"{rechnung.empfaenger_strasse}, {rechnung.empfaenger_ort}",
        rechnungsdatum=rechnung.rechnungsdatum,
        # Angebote nennen keinen Leistungszeitpunkt als Pflichtangabe
        leistung_von=rechnung.leistung_von if rechnung.ist_rechnung else rechnung.rechnungsdatum,
        hinweis_steuerbefreiung=rechnung.hinweis_steuerbefreiung,
        positionen_mit_betrag=sum(
            1 for p in rechnung.positionen if p.typ == "artikel" and p.bezeichnung
        ),
    )
    if rechnung.leistung_art == "leistungszeitraum" and not rechnung.leistung_bis:
        fehler.append("Ende des Leistungszeitraums fehlt.")
    if (
        rechnung.leistung_bis
        and rechnung.leistung_von
        and rechnung.leistung_bis < rechnung.leistung_von
    ):
        fehler.append("Der Leistungszeitraum endet vor seinem Beginn.")
    if any(p.typ == "artikel" and not p.bezeichnung for p in rechnung.positionen):
        fehler.append("Jede Position braucht eine Bezeichnung.")
    if rechnung.summe_cent < 0 and rechnung.belegart != "korrektur":
        fehler.append(
            "Der Gesamtbetrag darf nicht negativ sein. Dafür gibt es Rechnungskorrekturen."
        )
    if rechnung.qr_ueberweisung and rechnung.ist_rechnung:
        try:
            pruefe_iban(gewerbe.iban or "")
        except IbanFehler:
            fehler.append(
                "Für den QR-Code fehlt eine gültige Bankverbindung (Einstellungen → Rechnungen)."
            )
        if rechnung.summe_cent <= 0:
            fehler.append("Ein QR-Code ist nur bei einem Betrag über 0 € möglich.")
    return fehler


def _naechste_nummer(belegart: str) -> str:
    kreis = db.session.execute(
        select(Nummernkreis).where(Nummernkreis.belegart == belegart).with_for_update()
    ).scalar_one()
    nummer = formatiere_nummer(kreis.praefix, kreis.naechste_nummer, kreis.stellen)
    kreis.naechste_nummer += 1
    return nummer


def finalisiere(rechnung: Rechnung, nutzer_id: int) -> Rechnung:
    """Vergibt die Nummer, erzeugt das PDF/A, legt es ab und schreibt die Rechnung fest."""
    from app.services.pdf import rendere_rechnung

    _pruefe_entwurf(rechnung)
    gewerbe = aktuelles_gewerbe()
    fehler = finalisierungsfehler(rechnung, gewerbe)
    if fehler:
        raise NichtFinalisierbar(fehler)

    rechnung.nummer = _naechste_nummer(rechnung.belegart)
    if rechnung.ist_rechnung:
        rechnung.faellig_am = faellig_am(rechnung.rechnungsdatum, rechnung.zahlungsziel_tage)
    elif rechnung.belegart == "angebot":
        rechnung.gueltig_bis = faellig_am(rechnung.rechnungsdatum, gewerbe.angebot_gueltig_tage)
        rechnung.qr_ueberweisung = False
    else:
        rechnung.qr_ueberweisung = False
    rechnung.absender = absender_daten(gewerbe)
    rechnung.pdf_sha256 = ablage.speichere(rendere_rechnung(rechnung, entwurf=False))
    rechnung.finalisiert_am = datetime.now(UTC)
    rechnung.finalisiert_von = nutzer_id
    rechnung.status = "offen"
    protokolliere(
        f"{rechnung.belegart}_finalisiert",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={
            "nummer": rechnung.nummer,
            "summe_cent": rechnung.summe_cent,
            "pdf_sha256": rechnung.pdf_sha256,
        },
    )
    db.session.commit()
    return rechnung


def pdf(rechnung: Rechnung) -> bytes:
    """Finalisiert: das abgelegte Original. Entwurf: Vorschau mit Wasserzeichen."""
    from app.services.pdf import rendere_rechnung

    if rechnung.ist_entwurf:
        return rendere_rechnung(rechnung, entwurf=True)
    return ablage.lies(rechnung.pdf_sha256)


def suche_rechnungen(filter: str = "alle", angebote: bool = False) -> list[Rechnung]:
    """Rechnungen samt Korrekturen, oder (angebote=True) nur Angebote."""
    if angebote:
        abfrage = select(Rechnung).where(Rechnung.belegart == "angebot")
    else:
        abfrage = select(Rechnung).where(Rechnung.belegart.in_(["rechnung", "korrektur"]))
    if filter == "entwuerfe":
        abfrage = abfrage.where(Rechnung.status == "entwurf")
    elif filter == "offen":
        abfrage = abfrage.where(Rechnung.status.in_(["offen", "teilbezahlt"]))
        if not angebote:
            abfrage = abfrage.where(Rechnung.belegart == "rechnung")
    return list(
        db.session.execute(
            abfrage.order_by(Rechnung.rechnungsdatum.desc(), Rechnung.id.desc())
        ).scalars()
    )


# ---------- Angebote ----------


class AktionNichtMoeglich(ValueError):
    pass


def entscheide_angebot(angebot: Rechnung, angenommen: bool, nutzer_id: int) -> None:
    if angebot.belegart != "angebot" or angebot.ist_entwurf:
        raise AktionNichtMoeglich(
            "Nur finalisierte Angebote können angenommen oder abgelehnt werden."
        )
    angebot.status = "angenommen" if angenommen else "abgelehnt"
    protokolliere(
        f"angebot_{angebot.status}",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=angebot.id,
    )
    db.session.commit()


def rechnungen_zum_angebot(angebot: Rechnung) -> list[Rechnung]:
    """Rechnungen (auch Entwürfe), die aus dem Angebot entstanden sind, ohne stornierte."""
    return list(
        db.session.execute(
            select(Rechnung).where(
                Rechnung.belegart == "rechnung",
                Rechnung.bezug_id == angebot.id,
                Rechnung.status != "storniert",
            )
        ).scalars()
    )


def rechnung_aus_angebot(angebot: Rechnung, nutzer_id: int) -> Rechnung:
    """Neuer Rechnungsentwurf mit Kunde und Positionen des Angebots."""
    if angebot.belegart != "angebot" or angebot.ist_entwurf:
        raise AktionNichtMoeglich("Nur aus finalisierten Angeboten kann eine Rechnung entstehen.")
    if rechnungen_zum_angebot(angebot):
        raise AktionNichtMoeglich("Aus diesem Angebot gibt es schon eine Rechnung.")
    rechnung = neuer_entwurf(nutzer_id, "rechnung")
    for feld in (
        "kontakt_id",
        "empfaenger_name",
        "empfaenger_zusatz",
        "empfaenger_strasse",
        "empfaenger_plz",
        "empfaenger_ort",
        "empfaenger_land",
        "leistung_art",
        "leistung_von",
        "leistung_bis",
    ):
        setattr(rechnung, feld, getattr(angebot, feld))
    rechnung.bezug_id = angebot.id
    rechnung.positionen.clear()
    db.session.flush()
    for p in angebot.positionen:
        rechnung.positionen.append(_kopie(p))
    rechnung.summe_cent = angebot.summe_cent
    if angebot.status == "offen":
        angebot.status = "angenommen"
    protokolliere(
        "rechnung_aus_angebot",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={"angebot": angebot.nummer},
    )
    db.session.commit()
    return rechnung


def _kopie(p: Rechnungsposition, faktor: int = 1) -> Rechnungsposition:
    return Rechnungsposition(
        position=p.position,
        typ=p.typ,
        artikel_id=p.artikel_id,
        bezeichnung=p.bezeichnung,
        beschreibung=p.beschreibung,
        menge_tausendstel=p.menge_tausendstel,
        einheit=p.einheit,
        einzelpreis_cent=faktor * p.einzelpreis_cent,
        rabatt_bp=p.rabatt_bp,
        betrag_cent=faktor * p.betrag_cent,
    )


# ---------- Rechnungskorrektur ----------


def storniere_rechnung(rechnung: Rechnung, nutzer_id: int) -> Rechnung:
    """Vollstorno per Rechnungskorrektur. Die Originalrechnung bleibt unverändert erhalten."""
    if not rechnung.ist_rechnung or rechnung.ist_entwurf:
        raise AktionNichtMoeglich("Nur finalisierte Rechnungen können storniert werden.")
    if rechnung.status == "storniert":
        raise AktionNichtMoeglich("Diese Rechnung ist bereits storniert.")
    if rechnung.bezahlt_cent != 0:
        raise AktionNichtMoeglich(
            "Auf diese Rechnung ist schon Geld eingegangen. Bitte zuerst die Zahlung "
            "rückgängig machen oder die Rückzahlung erfassen."
        )
    korrektur = neuer_entwurf(nutzer_id, "korrektur", bezug_id=rechnung.id)
    for feld in (
        "kontakt_id",
        "empfaenger_name",
        "empfaenger_zusatz",
        "empfaenger_strasse",
        "empfaenger_plz",
        "empfaenger_ort",
        "empfaenger_land",
        "leistung_art",
        "leistung_von",
        "leistung_bis",
        "hinweis_steuerbefreiung",
    ):
        setattr(korrektur, feld, getattr(rechnung, feld))
    korrektur.bezug_id = rechnung.id
    korrektur.einleitung = (
        f"Hiermit stornieren wir die Rechnung {rechnung.nummer} vom "
        f"{rechnung.rechnungsdatum.strftime('%d.%m.%Y')} vollständig."
    )
    korrektur.nachbemerkung = None
    korrektur.positionen.clear()
    db.session.flush()
    for p in rechnung.positionen:
        korrektur.positionen.append(_kopie(p, faktor=-1))
    korrektur.summe_cent = -rechnung.summe_cent
    db.session.flush()
    finalisiere(korrektur, nutzer_id)
    rechnung.status = "storniert"
    protokolliere(
        "rechnung_storniert",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={"korrektur": korrektur.nummer},
    )
    db.session.commit()
    return korrektur


# ---------- Lieferschein ----------


def lieferscheine_zu(rechnung: Rechnung) -> list[Rechnung]:
    return list(
        db.session.execute(
            select(Rechnung)
            .where(Rechnung.belegart == "lieferschein", Rechnung.bezug_id == rechnung.id)
            .order_by(Rechnung.id)
        ).scalars()
    )


def lieferschein_aus_rechnung(rechnung: Rechnung, nutzer_id: int) -> Rechnung:
    """Lieferschein mit den Positionen der Rechnung, ohne Preise. Wird sofort finalisiert."""
    if not rechnung.ist_rechnung or rechnung.ist_entwurf:
        raise AktionNichtMoeglich(
            "Nur aus finalisierten Rechnungen kann ein Lieferschein entstehen."
        )
    if rechnung.status == "storniert":
        raise AktionNichtMoeglich("Zu einer stornierten Rechnung gibt es keinen Lieferschein.")
    if lieferscheine_zu(rechnung):
        raise AktionNichtMoeglich("Zu dieser Rechnung gibt es schon einen Lieferschein.")
    lieferschein = neuer_entwurf(nutzer_id, "lieferschein", bezug_id=rechnung.id)
    for feld in (
        "kontakt_id",
        "empfaenger_name",
        "empfaenger_zusatz",
        "empfaenger_strasse",
        "empfaenger_plz",
        "empfaenger_ort",
        "empfaenger_land",
        "leistung_art",
        "leistung_von",
        "leistung_bis",
        "hinweis_steuerbefreiung",
    ):
        setattr(lieferschein, feld, getattr(rechnung, feld))
    lieferschein.einleitung = None
    lieferschein.nachbemerkung = None
    lieferschein.positionen.clear()
    db.session.flush()
    for p in rechnung.positionen:
        kopie = _kopie(p, faktor=0)
        kopie.rabatt_bp = 0
        lieferschein.positionen.append(kopie)
    lieferschein.summe_cent = 0
    db.session.flush()
    return finalisiere(lieferschein, nutzer_id)


# ---------- Zusammenhang der Belege ----------

_REIHENFOLGE = {"rechnung": 0, "lieferschein": 1, "korrektur": 2}


def belegkette(aktuell: "Rechnung | Mahnung") -> list[dict]:  # noqa: F821
    """Alle zusammengehörigen Belege als Baum (Angebot → Rechnung → Lieferschein, Korrektur,
    Mahnungen), flach mit Einrückung. Der aktuelle Beleg ist markiert."""
    from app.models import Mahnung

    ausgang = aktuell.rechnung if isinstance(aktuell, Mahnung) else aktuell
    wurzel = ausgang
    while wurzel.bezug is not None:
        wurzel = wurzel.bezug
    eintraege: list[dict] = []

    def gehe(knoten: Rechnung, tiefe: int) -> None:
        eintraege.append(
            {"tiefe": tiefe, "beleg": knoten, "mahnung": None, "aktuell": knoten is aktuell}
        )
        for m in knoten.mahnungen:
            eintraege.append(
                {"tiefe": tiefe + 1, "beleg": knoten, "mahnung": m, "aktuell": m is aktuell}
            )
        kinder = db.session.execute(
            select(Rechnung).where(Rechnung.bezug_id == knoten.id).order_by(Rechnung.id)
        ).scalars()
        for kind in sorted(kinder, key=lambda k: _REIHENFOLGE.get(k.belegart, 9)):
            gehe(kind, tiefe + 1)

    gehe(wurzel, 0)
    return eintraege
