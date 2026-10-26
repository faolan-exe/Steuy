# ruff: noqa: E501, F811
import io
from datetime import date
from decimal import Decimal

import pytest
from lxml import etree
from pypdf import PdfReader

from app.domain.erechnung import aus_xml
from app.domain.zugferd import (
    GUIDELINE_EN16931,
    GUIDELINE_XRECHNUNG,
    ERechnung,
    Partei,
    Zeile,
    baue_xml,
    einheit_code,
    pruefe,
)
from app.models import Gewerbe, Kontakt
from app.services import ablage
from app.services.rechnungen import (
    NichtFinalisierbar,
    finalisiere,
    neuer_entwurf,
    storniere_rechnung,
)
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}


def stoff(**mehr) -> ERechnung:
    daten = dict(
        nummer="RE0001",
        datum=date(2026, 10, 26),
        faellig_am=date(2026, 11, 9),
        verkaeufer=Partei(
            "Andy Theke Fotograf",
            "Blendenweg 12",
            None,
            "50667",
            "Köln",
            "Deutschland",
            "Andy Theke",
            "0221 123456",
            "hallo@andy.example",
            "214/815/08150",
        ),
        kaeufer=Partei("Franz Ohse", "Birkenallee 3", None, "53111", "Bonn", "Deutschland"),
        zeilen=[
            Zeile(1, "Miete Kamera-Set", "Gehäuse", 3000, "Tag", 7900, 21330, 2370),
            Zeile(2, "Objektiv", None, 3000, "Tag", 3500, 10500),
        ],
        leistung_von=date(2026, 10, 1),
        leistung_bis=date(2026, 10, 31),
        iban="DE89 3704 0044 0532 0130 00",
        bic="COBADEFFXXX",
        kontoinhaber="Andy Theke",
    )
    daten.update(mehr)
    return ERechnung(**daten)


def baum(xml: bytes):
    return etree.fromstring(xml)


def wert(baum_, pfad: str) -> str | None:
    knoten = baum_.xpath(pfad, namespaces=NS)
    return knoten[0].text if knoten else None


# ---------- Aufbau des XML ----------


def test_kopf_summen_und_befreiung():
    x = baum(baue_xml(stoff()))
    assert wert(x, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == GUIDELINE_EN16931
    assert wert(x, "//rsm:ExchangedDocument/ram:ID") == "RE0001"
    assert wert(x, "//rsm:ExchangedDocument/ram:TypeCode") == "380"
    assert wert(x, "//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString") == "20261026"
    assert (
        wert(
            x,
            "//ram:LineTotalAmount[ancestor::ram:SpecifiedTradeSettlementHeaderMonetarySummation]",
        )
        == "318.30"
    )
    assert wert(x, "//ram:GrandTotalAmount") == "318.30"
    assert wert(x, "//ram:DuePayableAmount") == "318.30"
    assert wert(x, "//ram:TaxBasisTotalAmount") == "318.30"
    assert wert(x, "//ram:TaxTotalAmount") == "0.00"
    steuer = x.xpath("//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax", namespaces=NS)
    assert len(steuer) == 1
    assert (
        wert(steuer[0], "ram:CategoryCode") == "E"
        and wert(steuer[0], "ram:RateApplicablePercent") == "0.00"
    )
    assert "§ 19 UStG" in wert(steuer[0], "ram:ExemptionReason")
    assert (
        wert(x, "//ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString")
        == "20261109"
    )


def test_positionen_einheit_menge_rabatt():
    x = baum(baue_xml(stoff()))
    zeilen = x.xpath("//ram:IncludedSupplyChainTradeLineItem", namespaces=NS)
    assert len(zeilen) == 2
    z1 = zeilen[0]
    assert wert(z1, ".//ram:SpecifiedTradeProduct/ram:Name") == "Miete Kamera-Set"
    assert wert(z1, ".//ram:NetPriceProductTradePrice/ram:ChargeAmount") == "79.00"
    menge = z1.xpath(".//ram:BilledQuantity", namespaces=NS)[0]
    assert menge.text == "3" and menge.get("unitCode") == "DAY"
    assert wert(z1, ".//ram:SpecifiedTradeAllowanceCharge/ram:ActualAmount") == "23.70"
    assert (
        wert(z1, ".//ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount")
        == "213.30"
    )
    assert wert(zeilen[1], ".//ram:SpecifiedTradeAllowanceCharge/ram:ActualAmount") is None
    assert all(wert(z, ".//ram:ApplicableTradeTax/ram:CategoryCode") == "E" for z in zeilen)


def test_beteiligte_zahlung_und_ansprechpartner():
    x = baum(baue_xml(stoff()))
    verkaeufer = x.xpath("//ram:SellerTradeParty", namespaces=NS)[0]
    assert wert(verkaeufer, "ram:Name") == "Andy Theke Fotograf"
    assert wert(verkaeufer, "ram:PostalTradeAddress/ram:CountryID") == "DE"
    assert wert(verkaeufer, "ram:PostalTradeAddress/ram:CityName") == "Köln"
    assert (
        wert(
            verkaeufer,
            "ram:DefinedTradeContact/ram:TelephoneUniversalCommunication/ram:CompleteNumber",
        )
        == "0221 123456"
    )
    assert (
        wert(verkaeufer, "ram:DefinedTradeContact/ram:EmailURIUniversalCommunication/ram:URIID")
        == "hallo@andy.example"
    )
    reg = verkaeufer.xpath("ram:SpecifiedTaxRegistration/ram:ID", namespaces=NS)[0]
    assert reg.text == "214/815/08150" and reg.get("schemeID") == "FC"
    assert wert(x, "//ram:BuyerTradeParty/ram:Name") == "Franz Ohse"
    assert wert(x, "//ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode") == "58"
    assert (
        wert(x, "//ram:PayeePartyCreditorFinancialAccount/ram:IBANID") == "DE89370400440532013000"
    )
    assert wert(x, "//ram:PaymentReference") == "RE0001"


def test_zeitraum_und_einzeldatum():
    x = baum(baue_xml(stoff()))
    assert (
        wert(x, "//ram:BillingSpecifiedPeriod/ram:StartDateTime/udt:DateTimeString") == "20261001"
    )
    assert wert(x, "//ram:BillingSpecifiedPeriod/ram:EndDateTime/udt:DateTimeString") == "20261031"
    einzel = baum(baue_xml(stoff(leistung_bis=None)))
    assert wert(einzel, "//ram:BillingSpecifiedPeriod/ram:StartDateTime") is None
    assert (
        wert(
            einzel, "//ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime/udt:DateTimeString"
        )
        == "20261001"
    )


def test_leitweg_id_macht_aus_der_e_rechnung_eine_xrechnung():
    x = baum(baue_xml(stoff(kaeuferreferenz="04011000-1234512345-35")))
    assert wert(x, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == GUIDELINE_XRECHNUNG
    assert wert(x, "//ram:BuyerReference") == "04011000-1234512345-35"
    assert wert(baum(baue_xml(stoff())), "//ram:BuyerReference") is None


def test_rechnungskorrektur_wird_gutschrift_mit_bezug():
    x = baum(
        baue_xml(
            stoff(
                nummer="RK0001",
                korrektur=True,
                faellig_am=None,
                bezug_nummer="RE0001",
                bezug_datum=date(2026, 10, 1),
            )
        )
    )
    assert wert(x, "//rsm:ExchangedDocument/ram:TypeCode") == "381"
    assert wert(x, "//ram:InvoiceReferencedDocument/ram:IssuerAssignedID") == "RE0001"
    assert wert(x, "//ram:SpecifiedTradePaymentTerms") is None
    assert wert(x, "//ram:GrandTotalAmount") == "318.30"  # positiv, die Art macht die Gutschrift


def test_ausgabe_ist_maschinenlesbar_mit_dem_vorhandenen_leser():
    vorschlag = aus_xml(baue_xml(stoff()))
    assert vorschlag.betrag_cent == 31830 and vorschlag.belegnummer == "RE0001"
    assert vorschlag.datum == date(2026, 10, 26) and vorschlag.lieferant == "Andy Theke Fotograf"


def test_umlaute_und_sonderzeichen_im_text():
    r = stoff(zeilen=[Zeile(1, 'Größe <M> & "Co" ✓', "ä&ö", 1000, "Stück", 1000, 1000)])
    x = baum(baue_xml(r))
    assert wert(x, "//ram:SpecifiedTradeProduct/ram:Name") == 'Größe <M> & "Co" ✓'


@pytest.mark.parametrize(
    ("einheit", "code"),
    [
        ("Stunde", "HUR"),
        (" tage ", "DAY"),
        ("Stück", "C62"),
        ("Pauschale", "C62"),
        ("Kilometer", "KMT"),
        ("Monat", "MON"),
        ("Zeppelin", "C62"),
        (None, "C62"),
    ],
)
def test_einheiten(einheit, code):
    assert einheit_code(einheit) == code


def test_dezimalmengen():
    r = stoff(zeilen=[Zeile(1, "Anfahrt", None, 37500, "Kilometer", 60, 2250)])
    x = baum(baue_xml(r))
    assert x.xpath("//ram:BilledQuantity", namespaces=NS)[0].text == "37.5"
    assert wert(x, "//ram:GrandTotalAmount") == "22.50"


# ---------- Prüfung der Angaben ----------


def test_vollstaendige_angaben_haben_keine_fehler():
    assert pruefe(stoff()) == []


@pytest.mark.parametrize(
    ("aenderung", "stichwort"),
    [
        (
            {
                "verkaeufer": Partei(
                    "A", "S 1", None, "1", "O", "DE", None, "1", "a@b.de", None, None
                )
            },
            "Steuernummer",
        ),
        (
            {"verkaeufer": Partei("A", "S 1", None, "1", "O", "DE", None, None, None, "1/2/3")},
            "E-Mail und Telefon",
        ),
        (
            {"verkaeufer": Partei("A", None, None, None, None, "DE", None, "1", "a@b.de", "1/2/3")},
            "Anschrift",
        ),
        ({"kaeufer": Partei("")}, "Kunde braucht einen Namen"),
        ({"kaeufer": Partei("K", None, None, None, None)}, "Straße oder Ort"),
        ({"zeilen": []}, "keine Position"),
        ({"faellig_am": None}, "Fälligkeitsdatum"),
        ({"iban": None}, "Bankverbindung"),
    ],
)
def test_fehlende_angaben_werden_benannt(aenderung, stichwort):
    assert any(stichwort in f for f in pruefe(stoff(**aenderung)))


# ---------- Beim Festschreiben ----------


@pytest.fixture
def e_rechnung_an(session):
    gewerbe = session.get(Gewerbe, 1)
    gewerbe.e_rechnung = True
    gewerbe.telefon = "0221 123456"
    gewerbe.email = "kontakt@musterwerkstatt.example"
    session.commit()
    return gewerbe


@pytest.fixture
def entwurf(angemeldet, admin, kunde, bank, e_rechnung_an):  # noqa: F811
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde, rechnungsdatum="2026-10-26", leistung_von="2026-10-20")
    return rechnung


def anhaenge(pdf: bytes) -> dict[str, list[bytes]]:
    return PdfReader(io.BytesIO(pdf)).attachments


def test_finalisieren_bettet_das_xml_ins_pdf_ein(entwurf, admin, app, session):
    with app.app_context():
        r = finalisiere(entwurf, admin.id)
        pdf = ablage.lies(r.pdf_sha256)
        xml = ablage.lies(r.xml_sha256)
    assert pdf.startswith(b"%PDF")
    angehaengt = anhaenge(pdf)
    assert list(angehaengt) == ["factur-x.xml"]
    assert angehaengt["factur-x.xml"][0] == xml
    leser = PdfReader(io.BytesIO(pdf))
    xmp = leser.xmp_metadata
    assert xmp is not None
    assert b"EN 16931" in leser.trailer["/Root"]["/Metadata"].get_object().get_data()
    x = baum(xml)
    assert wert(x, "//rsm:ExchangedDocument/ram:ID") == r.nummer
    assert wert(x, "//ram:GrandTotalAmount") == "152.20"
    assert wert(x, "//ram:BuyerTradeParty/ram:Name") == "Café Sonnenschein"
    assert "ZUGFeRD" not in xml.decode()  # Kennung steht als Leitlinien-ID, nicht als Wort
    assert GUIDELINE_EN16931 in xml.decode()


def test_ohne_einstellung_bleibt_alles_wie_bisher(angemeldet, admin, kunde, bank, app, session):  # noqa: F811
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde, rechnungsdatum="2026-10-26", leistung_von="2026-10-20")
    with app.app_context():
        r = finalisiere(rechnung, admin.id)
        pdf = ablage.lies(r.pdf_sha256)
    assert r.xml_sha256 is None and anhaenge(pdf) == {}
    assert angemeldet.get(f"/rechnungen/{r.id}/xml").status_code == 404


def test_fehlende_angaben_verhindern_das_festschreiben_mit_klaren_hinweisen(
    angemeldet,
    admin,
    kunde,
    bank,
    app,
    session,  # noqa: F811
):
    session.get(Gewerbe, 1).e_rechnung = True
    session.commit()  # Telefon fehlt (E-Mail steht schon in den Firmendaten)
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde, rechnungsdatum="2026-10-26", leistung_von="2026-10-20")
    with app.app_context(), pytest.raises(NichtFinalisierbar) as fehler:
        finalisiere(rechnung, admin.id)
    assert any("E-Mail und Telefon" in f for f in fehler.value.fehler)
    assert rechnung.status == "entwurf" and rechnung.nummer is None
    vorschau = angemeldet.get(f"/rechnungen/{rechnung.id}/vorschau").get_data(as_text=True)
    assert "E-Mail und Telefon" in vorschau


def test_xml_download(angemeldet, entwurf, admin, app, session):
    with app.app_context():
        r = finalisiere(entwurf, admin.id)
        gespeichert = ablage.lies(r.xml_sha256)
    antwort = angemeldet.get(f"/rechnungen/{r.id}/xml")
    assert antwort.status_code == 200 and antwort.mimetype == "application/xml"
    assert antwort.data == gespeichert
    assert f'filename="{r.nummer}.xml"' in antwort.headers["Content-Disposition"]
    assert antwort.headers["X-Content-Type-Options"] == "nosniff"
    seite = angemeldet.get(f"/rechnungen/{r.id}").get_data(as_text=True)
    assert "E-Rechnung (XML)" in seite


def test_download_nur_angemeldet(app, entwurf, admin, session):
    with app.app_context():
        r = finalisiere(entwurf, admin.id)
    assert app.test_client().get(f"/rechnungen/{r.id}/xml").status_code == 302


def test_xml_ist_unveraenderlich_nach_aenderung_der_firmendaten(entwurf, admin, app, session):
    with app.app_context():
        r = finalisiere(entwurf, admin.id)
        vorher = ablage.lies(r.xml_sha256)
        session.get(Gewerbe, 1).name = "Ganz anders"
        session.commit()
        assert ablage.lies(r.xml_sha256) == vorher


def test_storno_erzeugt_gutschrift_xml(angemeldet, entwurf, admin, app, session):
    with app.app_context():
        original = finalisiere(entwurf, admin.id)
        korrektur = storniere_rechnung(original, admin.id)
        xml = ablage.lies(korrektur.xml_sha256)
        pdf = ablage.lies(korrektur.pdf_sha256)
    x = baum(xml)
    assert wert(x, "//rsm:ExchangedDocument/ram:TypeCode") == "381"
    assert wert(x, "//ram:InvoiceReferencedDocument/ram:IssuerAssignedID") == original.nummer
    assert wert(x, "//ram:GrandTotalAmount") == "152.20"
    assert anhaenge(pdf)["factur-x.xml"][0] == xml


def test_leitweg_id_vom_kunden_gibt_xrechnung(angemeldet, entwurf, admin, app, session):
    session.get(Kontakt, entwurf.kontakt_id).leitweg_id = "991-12345-67"
    session.commit()
    with app.app_context():
        r = finalisiere(entwurf, admin.id)
        xml = ablage.lies(r.xml_sha256)
        pdf = ablage.lies(r.pdf_sha256)
    x = baum(xml)
    assert wert(x, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == GUIDELINE_XRECHNUNG
    assert wert(x, "//ram:BuyerReference") == "991-12345-67"
    metadaten = PdfReader(io.BytesIO(pdf)).trailer["/Root"]["/Metadata"].get_object().get_data()
    assert b"XRECHNUNG" in metadaten and "factur-x.xml" in anhaenge(pdf)


def test_xml_im_jahresexport(angemeldet, entwurf, admin, app, session):
    with app.app_context():
        r = finalisiere(entwurf, admin.id)
    import zipfile

    antwort = angemeldet.get("/auswertung/export.zip?jahr=2026")
    zip_ = zipfile.ZipFile(io.BytesIO(antwort.data))
    assert f"rechnungen/{r.nummer}.xml" in zip_.namelist()
    gesamt = zipfile.ZipFile(io.BytesIO(angemeldet.get("/auswertung/gesamtexport.zip").data))
    assert f"ablage/{r.xml_sha256[:2]}/{r.xml_sha256}" in gesamt.namelist()


def test_einstellung_und_leitweg_feld_in_der_oberflaeche(angemeldet, session):
    html = angemeldet.get("/einstellungen/rechnungen").get_data(as_text=True)
    assert "E-Rechnung" in html and 'name="e_rechnung"' in html
    kontakt = angemeldet.get("/kontakte/neu").get_data(as_text=True)
    assert 'name="leitweg_id"' in kontakt


def test_einstellung_speichern(angemeldet, session, bank):  # noqa: F811
    gewerbe = session.get(Gewerbe, 1)
    daten = {
        "kontoinhaber": "Erika",
        "iban": gewerbe.iban,
        "praefix": "RE",
        "stellen": "4",
        "naechste_nummer": "1",
        "zahlungsziel_tage": "14",
        "angebot_gueltig_tage": "30",
        "hinweis_steuerbefreiung": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        "e_rechnung": "y",
    }
    antwort = angemeldet.post("/einstellungen/rechnungen", data=daten)
    assert antwort.status_code == 302
    session.refresh(gewerbe)
    assert gewerbe.e_rechnung is True


def test_betraege_stimmen_ueber_viele_positionen():
    """Die Summe aller Zeilen ist die Summe der Rechnung, auch mit krummen Beträgen."""
    zeilen = [Zeile(i, f"P{i}", None, 1000, "Stück", 333 + i, 333 + i) for i in range(1, 41)]
    r = stoff(zeilen=zeilen)
    x = baum(baue_xml(r))
    summe = sum(
        Decimal(b.text)
        for b in x.xpath(
            "//ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount", namespaces=NS
        )
    )
    assert wert(x, "//ram:GrandTotalAmount") == str(summe)
