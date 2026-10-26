"""E-Rechnung zu einer Rechnung: Daten sammeln, XML bauen, ins PDF einbetten (ZUGFeRD)."""

from app.domain.rechnung import faellig_am, positionsbetrag
from app.domain.zugferd import BEFREIUNG_STANDARD, ERechnung, Partei, Zeile, baue_xml, pruefe
from app.models import Rechnung


class ERechnungFehler(ValueError):
    def __init__(self, fehler: list[str]):
        super().__init__("; ".join(fehler))
        self.fehler = fehler


def _verkaeufer(absender: dict) -> Partei:
    return Partei(
        name=absender.get("name") or "",
        strasse=absender.get("strasse"),
        plz=absender.get("plz"),
        ort=absender.get("ort"),
        land="DE",
        ansprechpartner=absender.get("inhaber"),
        telefon=absender.get("telefon"),
        email=absender.get("email"),
        steuernummer=absender.get("steuernummer"),
        ust_idnr=absender.get("ust_idnr"),
    )


def _kaeufer(rechnung: Rechnung) -> Partei:
    kontakt = rechnung.kontakt
    return Partei(
        name=rechnung.empfaenger_name or "",
        strasse=rechnung.empfaenger_strasse,
        zusatz=rechnung.empfaenger_zusatz,
        plz=rechnung.empfaenger_plz,
        ort=rechnung.empfaenger_ort,
        land=rechnung.empfaenger_land or "Deutschland",
        email=kontakt.email if kontakt else None,
    )


def daten(rechnung: Rechnung, absender: dict) -> ERechnung:
    """Alle Angaben der Rechnung im Aufbau der E-Rechnung. Rechnungskorrekturen werden zur
    Gutschrift: Die Beträge sind dort positiv, die Zuordnung zur Rechnung steht im Bezug."""
    korrektur = rechnung.belegart == "korrektur"
    vorzeichen = -1 if korrektur else 1
    zeilen = []
    for p in (x for x in rechnung.positionen if x.typ == "artikel"):
        preis = vorzeichen * p.einzelpreis_cent
        betrag = vorzeichen * p.betrag_cent
        rabatt = positionsbetrag(preis, p.menge_tausendstel, 0) - betrag
        zeilen.append(
            Zeile(
                nummer=len(zeilen) + 1,
                name=p.bezeichnung,
                beschreibung=p.beschreibung,
                menge_tausendstel=p.menge_tausendstel,
                einheit=p.einheit,
                einzelpreis_cent=preis,
                betrag_cent=betrag,
                rabatt_cent=rabatt,
            )
        )
    bezug = rechnung.bezug if korrektur else None
    leistung_bis = rechnung.leistung_bis if rechnung.leistung_art == "leistungszeitraum" else None
    return ERechnung(
        nummer=rechnung.nummer or "Entwurf",
        datum=rechnung.rechnungsdatum,
        faellig_am=None
        if korrektur
        else rechnung.faellig_am or faellig_am(rechnung.rechnungsdatum, rechnung.zahlungsziel_tage),
        verkaeufer=_verkaeufer(absender),
        kaeufer=_kaeufer(rechnung),
        zeilen=zeilen,
        korrektur=korrektur,
        bezug_nummer=bezug.nummer if bezug else None,
        bezug_datum=bezug.rechnungsdatum if bezug else None,
        leistung_von=rechnung.leistung_von,
        leistung_bis=leistung_bis,
        hinweis_befreiung=rechnung.hinweis_steuerbefreiung or BEFREIUNG_STANDARD,
        iban=absender.get("iban"),
        bic=absender.get("bic"),
        kontoinhaber=absender.get("kontoinhaber"),
        kaeuferreferenz=(rechnung.kontakt.leitweg_id if rechnung.kontakt else None) or None,
        verwendungszweck=rechnung.nummer,
    )


def fehler(rechnung: Rechnung, absender: dict) -> list[str]:
    """Was für die E-Rechnung noch fehlt, in verständlichen Worten."""
    return pruefe(daten(rechnung, absender))


def erzeuge_xml(rechnung: Rechnung, absender: dict) -> bytes:
    d = daten(rechnung, absender)
    probleme = pruefe(d)
    if probleme:
        raise ERechnungFehler(probleme)
    return baue_xml(d)


def einbetten(pdf: bytes, xml: bytes, absender: dict, rechnung: Rechnung) -> bytes:
    """Das XML als Anhang ins PDF/A-3 legen (ZUGFeRD / Factur-X, bei Leitweg-ID XRechnung)."""
    from drafthorse.pdf import attach_xml

    stufe = "XRECHNUNG" if rechnung.kontakt and rechnung.kontakt.leitweg_id else "EN 16931"
    return attach_xml(pdf, xml, stufe)


def ist_erechnung_art(rechnung: Rechnung) -> bool:
    return rechnung.belegart in ("rechnung", "korrektur")
