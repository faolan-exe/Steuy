"""E-Rechnung erzeugen: ZUGFeRD / Factur-X (EN 16931) und XRechnung als CII-XML.

Reine Fachlogik ohne Flask und Datenbank. Beträge kommen als ganze Cent und werden hier
exakt in Dezimalzahlen mit zwei Stellen umgerechnet. steuy ist für Kleinunternehmer (§ 19 UStG):
Jede Position und die Zusammenfassung tragen die Steuerkategorie „E“ (befreit) mit 0 Prozent
und dem Befreiungsgrund aus dem Hinweistext der Rechnung.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from drafthorse.models.accounting import ApplicableTradeTax, TradeAllowanceCharge
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.models.tradelines import LineItem

GUIDELINE_EN16931 = "urn:cen.eu:en16931:2017"
GUIDELINE_XRECHNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
TYP_RECHNUNG = "380"
TYP_GUTSCHRIFT = "381"  # Rechnungskorrektur (Storno): Beträge sind in der E-Rechnung positiv
BEFREIUNG_STANDARD = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."

# Mengeneinheiten aus der Praxis auf UN/ECE-Recommendation-20-Codes. Unbekanntes wird „Stück“.
EINHEITEN = {
    "stück": "C62",
    "stk": "C62",
    "stk.": "C62",
    "stueck": "C62",
    "pauschale": "C62",
    "einheit": "C62",
    "stunde": "HUR",
    "stunden": "HUR",
    "std": "HUR",
    "std.": "HUR",
    "h": "HUR",
    "tag": "DAY",
    "tage": "DAY",
    "woche": "WEE",
    "wochen": "WEE",
    "monat": "MON",
    "monate": "MON",
    "jahr": "ANN",
    "jahre": "ANN",
    "kilometer": "KMT",
    "km": "KMT",
    "meter": "MTR",
    "m": "MTR",
    "quadratmeter": "MTK",
    "m²": "MTK",
    "liter": "LTR",
    "l": "LTR",
    "kilogramm": "KGM",
    "kg": "KGM",
    "gramm": "GRM",
    "g": "GRM",
    "satz": "SET",
    "set": "SET",
    "paar": "PR",
    "seite": "C62",
    "seiten": "C62",
}


def einheit_code(einheit: str | None) -> str:
    return EINHEITEN.get((einheit or "").strip().lower(), "C62")


def euro(cent: int) -> Decimal:
    return (Decimal(cent) / 100).quantize(Decimal("0.01"))


def menge(tausendstel: int) -> Decimal:
    return (Decimal(tausendstel) / 1000).normalize()


@dataclass
class Partei:
    name: str
    strasse: str | None = None
    zusatz: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str = "DE"
    ansprechpartner: str | None = None
    telefon: str | None = None
    email: str | None = None
    steuernummer: str | None = None
    ust_idnr: str | None = None


@dataclass
class Zeile:
    nummer: int
    name: str
    beschreibung: str | None
    menge_tausendstel: int
    einheit: str | None
    einzelpreis_cent: int  # Preis je Einheit vor Rabatt
    betrag_cent: int  # Zeilensumme nach Rabatt
    rabatt_cent: int = 0


@dataclass
class ERechnung:
    nummer: str
    datum: date
    faellig_am: date | None
    verkaeufer: Partei
    kaeufer: Partei
    zeilen: list[Zeile]
    korrektur: bool = False
    bezug_nummer: str | None = None  # Rechnung, die korrigiert wird
    bezug_datum: date | None = None
    leistung_von: date | None = None
    leistung_bis: date | None = None
    hinweis_befreiung: str = BEFREIUNG_STANDARD
    iban: str | None = None
    bic: str | None = None
    kontoinhaber: str | None = None
    kaeuferreferenz: str | None = None  # Leitweg-ID oder Bestellnummer, macht daraus XRechnung
    verwendungszweck: str | None = None
    notiz: str | None = None
    fehler: list[str] = field(default_factory=list)

    @property
    def summe_cent(self) -> int:
        return sum(z.betrag_cent for z in self.zeilen)

    @property
    def ist_xrechnung(self) -> bool:
        return bool(self.kaeuferreferenz)


def pruefe(r: ERechnung) -> list[str]:
    """Fehlende Angaben in verständlichen Worten (leer = in Ordnung)."""
    fehler = []
    v, k = r.verkaeufer, r.kaeufer
    if not v.name:
        fehler.append("Dein Firmenname fehlt.")
    if not (v.strasse and v.plz and v.ort):
        fehler.append("Deine Anschrift ist unvollständig (Einstellungen → Firmendaten).")
    if not (v.steuernummer or v.ust_idnr):
        fehler.append(
            "Für die E-Rechnung braucht es deine Steuernummer oder USt-IdNr. "
            "(Einstellungen → Firmendaten)."
        )
    if not (v.email and v.telefon):
        fehler.append(
            "Für die E-Rechnung braucht es E-Mail und Telefon als Ansprechstelle "
            "(Einstellungen → Firmendaten)."
        )
    if not k.name:
        fehler.append("Der Kunde braucht einen Namen.")
    if not (k.strasse and k.ort):
        fehler.append("Beim Kunden fehlt Straße oder Ort.")
    if not r.zeilen:
        fehler.append("Die Rechnung hat keine Position.")
    if r.summe_cent > 0 and not r.korrektur and not r.faellig_am:
        fehler.append("Es fehlt das Fälligkeitsdatum.")
    if r.summe_cent > 0 and not r.korrektur and not r.iban:
        fehler.append(
            "Für die E-Rechnung braucht es deine Bankverbindung (Einstellungen → Rechnungen)."
        )
    if r.korrektur and not r.bezug_nummer:
        fehler.append("Zur Rechnungskorrektur fehlt die ursprüngliche Rechnung.")
    return fehler


def _land(land: str | None) -> str:
    """Ländername oder -kürzel auf einen ISO-Code. Unbekannt wird DE (Standard von steuy)."""
    namen = {
        "deutschland": "DE",
        "germany": "DE",
        "österreich": "AT",
        "oesterreich": "AT",
        "schweiz": "CH",
        "niederlande": "NL",
        "frankreich": "FR",
        "italien": "IT",
        "spanien": "ES",
        "polen": "PL",
        "belgien": "BE",
        "luxemburg": "LU",
        "dänemark": "DK",
        "tschechien": "CZ",
    }
    text = (land or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", text):
        return text.upper()
    return namen.get(text.lower(), "DE")


def _partei(ziel, p: Partei, mit_kontakt: bool) -> None:
    ziel.name = p.name
    ziel.address.country_id = _land(p.land)
    if p.strasse:
        ziel.address.line_one = p.strasse
    if p.zusatz:
        ziel.address.line_two = p.zusatz
    if p.plz:
        ziel.address.postcode = p.plz
    if p.ort:
        ziel.address.city_name = p.ort
    if mit_kontakt:
        if p.ansprechpartner:
            ziel.contact.person_name = p.ansprechpartner
        if p.telefon:
            ziel.contact.telephone.number = p.telefon
        if p.email:
            ziel.contact.email.address = p.email
    elif p.email:
        ziel.electronic_address.uri_ID = ("EM", p.email)


def baue_xml(r: ERechnung) -> bytes:
    """CII-XML nach EN 16931 (bei Käuferreferenz mit XRechnung-Kennung). Prüft gegen das Schema."""
    doc = Document()
    doc.context.guideline_parameter.id = (
        GUIDELINE_XRECHNUNG if r.ist_xrechnung else GUIDELINE_EN16931
    )
    doc.header.id = r.nummer
    doc.header.type_code = TYP_GUTSCHRIFT if r.korrektur else TYP_RECHNUNG
    doc.header.issue_date_time = r.datum
    hinweis = IncludedNote()
    hinweis.content = r.hinweis_befreiung or BEFREIUNG_STANDARD
    doc.header.notes.add(hinweis)
    if r.notiz:
        zusatz = IncludedNote()
        zusatz.content = r.notiz
        doc.header.notes.add(zusatz)

    vertrag = doc.trade.agreement
    _partei(vertrag.seller, r.verkaeufer, mit_kontakt=True)
    if r.verkaeufer.steuernummer:
        vertrag.seller.tax_registrations.add(TaxRegistration(id=("FC", r.verkaeufer.steuernummer)))
    if r.verkaeufer.ust_idnr:
        vertrag.seller.tax_registrations.add(TaxRegistration(id=("VA", r.verkaeufer.ust_idnr)))
    _partei(vertrag.buyer, r.kaeufer, mit_kontakt=False)
    if r.kaeuferreferenz:
        vertrag.buyer_reference = r.kaeuferreferenz

    abrechnung = doc.trade.settlement
    abrechnung.currency_code = "EUR"
    if r.verwendungszweck or r.nummer:
        abrechnung.payment_reference = r.verwendungszweck or r.nummer
    if r.iban:
        zahlung = PaymentMeans()
        zahlung.type_code = "58"  # SEPA-Überweisung
        zahlung.payee_account.iban = r.iban.replace(" ", "")
        if r.kontoinhaber:
            zahlung.payee_account.account_name = r.kontoinhaber
        if r.bic:
            zahlung.payee_institution.bic = r.bic
        abrechnung.payment_means.add(zahlung)
    if r.leistung_von and r.leistung_bis and r.leistung_bis != r.leistung_von:
        abrechnung.period.start = r.leistung_von
        abrechnung.period.end = r.leistung_bis
    elif r.leistung_von:
        doc.trade.delivery.event.occurrence = r.leistung_von
    if r.bezug_nummer:
        abrechnung.invoice_referenced_document.issuer_assigned_id = r.bezug_nummer
        if r.bezug_datum:
            abrechnung.invoice_referenced_document.issue_date_time = r.bezug_datum

    for z in r.zeilen:
        zeile = LineItem()
        zeile.document.line_id = str(z.nummer)
        zeile.product.name = z.name or "Position"
        if z.beschreibung:
            zeile.product.description = z.beschreibung
        m = menge(z.menge_tausendstel)
        zeile.agreement.net.amount = euro(z.einzelpreis_cent)
        if z.rabatt_cent:
            # Rabatt als Nachlass auf die Zeile: Preis mal Menge minus Nachlass ist die Summe
            nachlass = TradeAllowanceCharge()
            nachlass.indicator = False
            nachlass.actual_amount = euro(z.rabatt_cent)
            nachlass.reason_code = "95"
            nachlass.reason = "Rabatt"
            zeile.settlement.allowance_charge.add(nachlass)
        zeile.delivery.billed_quantity = (m, einheit_code(z.einheit))
        zeile.settlement.trade_tax.type_code = "VAT"
        zeile.settlement.trade_tax.category_code = "E"
        zeile.settlement.trade_tax.rate_applicable_percent = Decimal("0")
        zeile.settlement.monetary_summation.total_amount = euro(z.betrag_cent)
        doc.trade.items.add(zeile)

    steuer = ApplicableTradeTax()
    steuer.calculated_amount = Decimal("0.00")
    steuer.basis_amount = euro(r.summe_cent)
    steuer.type_code = "VAT"
    steuer.category_code = "E"
    steuer.rate_applicable_percent = Decimal("0.00")
    steuer.exemption_reason = r.hinweis_befreiung or BEFREIUNG_STANDARD
    abrechnung.trade_tax.add(steuer)

    if r.faellig_am:
        bedingung = PaymentTerms()
        bedingung.due = r.faellig_am
        abrechnung.terms.add(bedingung)

    summe = abrechnung.monetary_summation
    gesamt = euro(r.summe_cent)
    summe.line_total = gesamt
    summe.charge_total = Decimal("0.00")
    summe.allowance_total = Decimal("0.00")
    summe.tax_basis_total = gesamt
    summe.tax_total = (Decimal("0.00"), "EUR")
    summe.grand_total = gesamt
    summe.due_amount = gesamt
    return doc.serialize(schema="FACTUR-X_EN16931")
