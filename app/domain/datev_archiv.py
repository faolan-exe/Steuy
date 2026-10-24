"""Belegarchiv im DATEV-Format (Belegbilder mit Belegdaten), z. B. aus Lexware Office, lesen.

Das ZIP enthält `document.xml` (Verzeichnis), je Beleg eine XML-Datei mit den Buchungsdaten
und das zugehörige PDF. Gelesen wird nur, nichts wird entpackt oder ausgeführt.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.domain.geld import GeldFormatFehler, euro_zu_cent

MAX_EINTRAEGE = 2000
MAX_ENTPACKT = 400 * 1024 * 1024
MAX_PDF = 20 * 1024 * 1024
ARTEN = {"accountsReceivableLedger": "einnahme", "accountsPayableLedger": "ausgabe"}

# Lexware-Kontonummer (SKR) → Kategorie in steuy. Was hier fehlt, wird als Entwurf angelegt und
# erscheint unter „Zu prüfen“. Fachliche Zuordnungen (Bewirtung, Anschaffungen) rät steuy nicht.
KATEGORIE_NACH_KONTO = {
    "4184": "Umsatzerlöse",
    "4185": "Umsatzerlöse",
    "5100": "Waren und Material",
    "5200": "Waren und Material",
    "6837": "Software und Abos",
    "6810": "Telefon und Internet",
    "6815": "Büromaterial",
    "6660": "Reisekosten",
    "6673": "Reisekosten",
    "6680": "Reisekosten",
    "6300": "Sonstige Ausgaben",
    "6825": "Sonstige Ausgaben",
}
BEWIRTUNG = "6640"
BEWIRTUNG_NICHT_ABZUGSFAEHIG = "6644"


class ArchivUngueltig(ValueError):
    pass


@dataclass
class Posten:
    konto: str
    kontoname: str
    betrag_cent: int


@dataclass
class Eintrag:
    guid: str
    art: str
    datum: date
    faellig: date | None
    rechnungsnr: str | None
    partner_nr: int | None
    partner: str | None
    ort: str | None
    ust_idnr: str | None
    info: str | None
    posten: list[Posten] = field(default_factory=list)
    pdf_name: str | None = None
    pdf: bytes | None = None

    @property
    def gesamt_cent(self) -> int:
        return sum(p.betrag_cent for p in self.posten)

    @property
    def konto(self) -> str:
        return self.posten[0].konto if self.posten else ""

    @property
    def kontoname(self) -> str:
        return self.posten[0].kontoname if self.posten else ""

    @property
    def schluessel(self) -> tuple:
        return (self.art, self.rechnungsnr, self.datum, self.gesamt_cent, self.partner)


def _text(knoten: Element, name: str) -> str | None:
    for kind in knoten:
        if kind.tag.rsplit("}", 1)[-1] == name:
            return (kind.text or "").strip() or None
    return None


def _datum(wert: str | None) -> date | None:
    if not wert:
        return None
    try:
        return date.fromisoformat(wert[:10])
    except ValueError:
        return None


def _cent(wert: str | None) -> int:
    try:
        return euro_zu_cent(wert or "")
    except GeldFormatFehler as fehler:
        raise ArchivUngueltig(f"Ungültiger Betrag „{wert}“.") from fehler


def _nummer(wert: str | None) -> int | None:
    return int(wert) if wert and re.fullmatch(r"\d{1,9}", wert) else None


def _eintrag_aus_xml(inhalt: bytes, guid: str, art: str) -> Eintrag:
    try:
        wurzel = ElementTree.fromstring(inhalt)
    except (ElementTree.ParseError, DefusedXmlException) as fehler:
        raise ArchivUngueltig("Die Buchungsdaten sind keine gültige XML-Datei.") from fehler
    zeilen = [
        z
        for sammel in wurzel
        for z in sammel
        if z.tag.rsplit("}", 1)[-1] in ARTEN and sammel.tag.rsplit("}", 1)[-1] == "consolidate"
    ]
    if not zeilen:
        raise ArchivUngueltig("Keine Buchungszeile gefunden.")
    erste = zeilen[0]
    datum = _datum(_text(erste, "date"))
    if datum is None:
        raise ArchivUngueltig("Das Belegdatum fehlt.")
    ist_kunde = art == "einnahme"
    eintrag = Eintrag(
        guid=guid,
        art=art,
        datum=datum,
        faellig=_datum(_text(erste, "dueDate")),
        rechnungsnr=_text(erste, "invoiceId"),
        partner_nr=_nummer(_text(erste, "partyId")),
        partner=_text(erste, "customerName" if ist_kunde else "supplierName"),
        ort=_text(erste, "customerCity" if ist_kunde else "supplierCity"),
        ust_idnr=_text(erste, "vatId"),
        info=_text(erste, "information"),
    )
    for zeile in zeilen:
        eintrag.posten.append(
            Posten(
                konto=_text(zeile, "accountNo") or "",
                kontoname=_text(zeile, "accountName") or "",
                betrag_cent=_cent(_text(zeile, "amount")),
            )
        )
    return eintrag


def _verzeichnis(inhalt: bytes) -> list[tuple[str, str, str, str | None]]:
    """(guid, Art, XML-Dateiname, PDF-Dateiname) je Beleg aus document.xml."""
    try:
        wurzel = ElementTree.fromstring(inhalt)
    except (ElementTree.ParseError, DefusedXmlException) as fehler:
        raise ArchivUngueltig("document.xml ist keine gültige XML-Datei.") from fehler
    ergebnis = []
    for dokument in wurzel.iter():
        if dokument.tag.rsplit("}", 1)[-1] != "document":
            continue
        xml_datei = pdf_datei = art = None
        for erweiterung in dokument:
            typ = next((v for k, v in erweiterung.attrib.items() if k.endswith("}type")), "")
            if erweiterung.get("datafile") and typ in ARTEN:
                xml_datei, art = erweiterung.get("datafile"), ARTEN[typ]
            elif typ == "File":
                pdf_datei = erweiterung.get("name")
        if xml_datei and art:
            ergebnis.append((dokument.get("guid") or xml_datei, art, xml_datei, pdf_datei))
    return ergebnis


def lies_archiv(inhalt: bytes) -> tuple[list[Eintrag], list[str]]:
    """Gibt (Einträge, Probleme) zurück. Defekte Belege werden gemeldet, nicht abgebrochen."""
    try:
        archiv = zipfile.ZipFile(io.BytesIO(inhalt))
    except zipfile.BadZipFile as fehler:
        raise ArchivUngueltig("Das ist keine ZIP-Datei.") from fehler
    with archiv:
        infos = {i.filename: i for i in archiv.infolist() if not i.is_dir()}
        if sum(i.file_size for i in infos.values()) > MAX_ENTPACKT:
            raise ArchivUngueltig("Das Archiv ist entpackt zu groß.")
        if "document.xml" not in infos:
            raise ArchivUngueltig(
                "document.xml fehlt. Bitte das ZIP „DATEV-Export Belegbilder mit Belegdaten“ "
                "aus Lexware hochladen."
            )
        verzeichnis = _verzeichnis(archiv.read("document.xml"))
        if len(verzeichnis) > MAX_EINTRAEGE:
            raise ArchivUngueltig(f"Mehr als {MAX_EINTRAEGE} Belege in einer Datei.")
        eintraege, probleme = [], []
        for guid, art, xml_datei, pdf_datei in verzeichnis:
            try:
                if xml_datei not in infos:
                    raise ArchivUngueltig("Buchungsdaten fehlen im Archiv.")
                eintrag = _eintrag_aus_xml(archiv.read(xml_datei), guid, art)
                if pdf_datei and pdf_datei in infos and infos[pdf_datei].file_size <= MAX_PDF:
                    eintrag.pdf_name, eintrag.pdf = pdf_datei, archiv.read(pdf_datei)
                eintraege.append(eintrag)
            except ArchivUngueltig as fehler:
                probleme.append(f"{xml_datei}: {fehler}")
        return eintraege, probleme


def bewirtung_prozent(eintrag: Eintrag) -> int | None:
    """Bewirtung ist in Lexware zweigeteilt (abzugsfähig / nicht abzugsfähig). In steuy ist das
    ein Beleg mit betrieblichem Anteil. Nur wenn der Anteil ganzzahlig aufgeht, wird er gesetzt."""
    konten = {p.konto: p.betrag_cent for p in eintrag.posten}
    if set(konten) != {BEWIRTUNG, BEWIRTUNG_NICHT_ABZUGSFAEHIG} or len(eintrag.posten) != 2:
        return None
    gesamt = eintrag.gesamt_cent
    if gesamt <= 0 or (konten[BEWIRTUNG] * 100) % gesamt:
        return None
    return konten[BEWIRTUNG] * 100 // gesamt


def ist_bewirtung(eintrag: Eintrag) -> bool:
    return any(p.konto in (BEWIRTUNG, BEWIRTUNG_NICHT_ABZUGSFAEHIG) for p in eintrag.posten)
