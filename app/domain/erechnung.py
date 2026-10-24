"""Kopfdaten aus E-Rechnungen (XRechnung UBL/CII, ZUGFeRD/Factur-X) lesen."""

from datetime import date
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.domain.belegerkennung import Vorschlag
from app.domain.geld import GeldFormatFehler, euro_zu_cent

XML_ANHAENGE = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml", "zugferd.xml")


class ERechnungFehler(ValueError):
    pass


def _text(element: Element, pfad: str) -> str | None:
    gefunden = element.find(pfad)
    return gefunden.text.strip() if gefunden is not None and gefunden.text else None


def _betrag(element: Element, *pfade: str) -> tuple[int | None, str | None]:
    for pfad in pfade:
        gefunden = element.find(pfad)
        if gefunden is not None and gefunden.text:
            try:
                return euro_zu_cent(gefunden.text.strip()), gefunden.get("currencyID")
            except GeldFormatFehler:
                continue
    return None, None


def aus_xml(inhalt: bytes) -> Vorschlag:
    try:
        wurzel = ElementTree.fromstring(inhalt)
    except (ElementTree.ParseError, DefusedXmlException) as fehler:
        raise ERechnungFehler("Die XML-Datei ist keine lesbare E-Rechnung.") from fehler

    name = wurzel.tag.rsplit("}", 1)[-1]
    if name == "Invoice" or name == "CreditNote":
        return _ubl(wurzel)
    if name == "CrossIndustryInvoice":
        return _cii(wurzel)
    raise ERechnungFehler("Unbekanntes XML-Format, keine XRechnung oder ZUGFeRD-Rechnung.")


def _ubl(w: Element) -> Vorschlag:
    partei = "{*}AccountingSupplierParty/{*}Party/"
    betrag, waehrung = _betrag(w, "{*}LegalMonetaryTotal/{*}PayableAmount")
    datum = _text(w, "{*}IssueDate")
    return Vorschlag(
        quelle="xrechnung",
        lieferant=_text(w, partei + "{*}PartyLegalEntity/{*}RegistrationName")
        or _text(w, partei + "{*}PartyName/{*}Name"),
        datum=date.fromisoformat(datum) if datum else None,
        belegnummer=_text(w, "{*}ID"),
        betrag_cent=betrag,
        hinweis=_waehrungshinweis(waehrung),
    )


def _cii(w: Element) -> Vorschlag:
    summen = ".//{*}SpecifiedTradeSettlementHeaderMonetarySummation/"
    betrag, waehrung = _betrag(w, summen + "{*}DuePayableAmount", summen + "{*}GrandTotalAmount")
    roh = _text(w, ".//{*}ExchangedDocument/{*}IssueDateTime/{*}DateTimeString")
    datum = None
    if roh and len(roh) == 8 and roh.isdigit():
        datum = date(int(roh[:4]), int(roh[4:6]), int(roh[6:]))
    return Vorschlag(
        quelle="zugferd",
        lieferant=_text(w, ".//{*}SellerTradeParty/{*}Name"),
        datum=datum,
        belegnummer=_text(w, ".//{*}ExchangedDocument/{*}ID"),
        betrag_cent=betrag,
        hinweis=_waehrungshinweis(waehrung),
    )


def _waehrungshinweis(waehrung: str | None) -> str | None:
    if waehrung and waehrung != "EUR":
        return f"Achtung: Rechnung in {waehrung}, bitte den Euro-Betrag eintragen."
    return None
