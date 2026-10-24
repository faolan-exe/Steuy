import io
import zipfile

import pytest
from sqlalchemy import select

from app.domain.datev_archiv import ArchivUngueltig, bewirtung_prozent, lies_archiv
from app.models import Beleg, Buchung, Kontakt
from app.services.archivimport import importiere_archiv
from tests.test_belege import text_pdf


@pytest.fixture(autouse=True)
def app_kontext(app, session):
    with app.app_context():
        yield


DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<archive xmlns="http://xml.datev.de/bedi/tps/document/v05.0" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><content>{docs}</content></archive>'
)
DOKUMENT = (
    '<document guid="{g}"><extension datafile="{g}.xml" xsi:type="{typ}"/>'
    '<extension xsi:type="File" name="{g}.pdf"/></document>'
)
LEDGER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<LedgerImport xmlns="http://xml.datev.de/bedi/tps/ledger/v050"><consolidate>{zeilen}'
    "</consolidate></LedgerImport>"
)
ZEILE = (
    "<{tag}><date>{datum}</date><amount>{betrag}</amount><accountNo>{konto}</accountNo>"
    "<tax>0.00</tax><information>{info}</information><invoiceId>{nr}</invoiceId>"
    "<partyId>{partei}</partyId><accountName>{kontoname}</accountName>"
    "<dueDate>2025-12-27</dueDate><{rolle}Name>{name}</{rolle}Name>"
    "<{rolle}City>Leipzig</{rolle}City></{tag}>"
)


def beleg(
    nr, betrag, art="ausgabe", konto="6837", datum="2025-03-01", name="Muster Verlag", teile=None
):
    ausgang = art == "einnahme"
    zeilen = teile or [(betrag, konto, "Konto")]
    return {
        "g": f"guid-{nr}-{betrag}",
        "typ": "accountsReceivableLedger" if ausgang else "accountsPayableLedger",
        "xml": LEDGER.format(
            zeilen="".join(
                ZEILE.format(
                    tag="accountsReceivableLedger" if ausgang else "accountsPayableLedger",
                    datum=datum,
                    betrag=b,
                    konto=k,
                    kontoname=kn,
                    info="Info",
                    nr=nr,
                    partei=70001,
                    rolle="customer" if ausgang else "supplier",
                    name=name,
                )
                for b, k, kn in zeilen
            )
        ),
        "pdf": text_pdf(f"Beleg {nr} {betrag}"),
    }


def archiv(*belege, ohne_verzeichnis=False):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        if not ohne_verzeichnis:
            z.writestr(
                "document.xml",
                DOC.format(docs="".join(DOKUMENT.format(g=b["g"], typ=b["typ"]) for b in belege)),
            )
        for b in belege:
            z.writestr(f"{b['g']}.xml", b["xml"])
            z.writestr(f"{b['g']}.pdf", b["pdf"])
    return puffer.getvalue()


def test_lesen_und_bewirtung():
    teile = [("47.25", "6640", "Bewirtungskosten"), ("20.25", "6644", "Nicht abzugsfähig")]
    eintraege, probleme = lies_archiv(archiv(beleg("B1", "67.50", teile=teile)))
    assert probleme == []
    assert eintraege[0].gesamt_cent == 6750
    assert bewirtung_prozent(eintraege[0]) == 70


def test_import_legt_offene_buchungen_an(admin, session):
    ergebnis = importiere_archiv(
        archiv(
            beleg("A1", "119.00"),
            beleg("A2", "50.00", art="einnahme", konto="4185", name="Muster Cafe"),
            beleg("A3", "10.00", konto="9999"),
            beleg("A4", "-5.00"),
        ),
        admin.id,
    )
    assert (ergebnis.festgeschrieben, ergebnis.entwuerfe) == (2, 1)
    assert len(ergebnis.gutschriften) == 1
    buchungen = {b.belegnummer: b for b in session.execute(select(Buchung)).scalars()}
    assert buchungen["A1"].status == "festgeschrieben"
    assert buchungen["A1"].zahlstatus == "offen"
    assert buchungen["A1"].zahlungen == []
    assert buchungen["A1"].betrag_cent == 11900
    assert buchungen["A1"].kategorie.name == "Software und Abos"
    assert buchungen["A2"].art == "einnahme"
    assert buchungen["A3"].status == "entwurf" and buchungen["A3"].kategorie_id is None
    assert "A4" not in buchungen
    from app.services.zahlungen import zu_pruefen

    offen = zu_pruefen()
    assert [b.belegnummer for b in offen["offene_einnahmen"]] == ["A2"]
    assert {b.belegnummer for b in offen["offene_ausgaben"]} == {"A1"}
    assert all(b.beleg_id for b in buchungen.values())
    # Ein Kontakt je Name, nicht je Beleg
    namen = [k.firmenname for k in session.execute(select(Kontakt)).scalars()]
    assert sorted(namen) == ["Muster Cafe", "Muster Verlag"]


def test_storno_aus_lexware_storniert_das_original(admin, session):
    daten = archiv(
        beleg("RE1", "-350.00", art="einnahme", konto="4185", name="Muster Cafe"),
        beleg("RE1", "350.00", art="einnahme", konto="4185", name="Muster Cafe"),
        beleg("RE2", "20.00", art="einnahme", konto="4185", name="Muster Cafe"),
    )
    vorschau = importiere_archiv(daten, admin.id, pruefen=True)
    assert (vorschau.storniert, vorschau.gutschriften) == (1, [])
    ergebnis = importiere_archiv(daten, admin.id)
    assert (ergebnis.festgeschrieben, ergebnis.storniert, ergebnis.gutschriften) == (2, 1, [])
    buchungen = list(session.execute(select(Buchung)).scalars())
    original = next(b for b in buchungen if b.belegnummer == "RE1" and b.betrag_cent > 0)
    assert original.storniert
    assert sum(b.betrag_cent for b in buchungen if b.belegnummer == "RE1") == 0
    # Wiederholung ändert nichts
    nochmal = importiere_archiv(daten, admin.id)
    assert nochmal.neu == 0 and nochmal.storniert == 0
    assert len(session.execute(select(Buchung)).all()) == 3


def test_stornierter_entwurf_wird_nicht_uebernommen(admin, session):
    daten = archiv(beleg("E1", "-9.00", konto="9999"), beleg("E1", "9.00", konto="9999"))
    ergebnis = importiere_archiv(daten, admin.id)
    assert (ergebnis.neu, ergebnis.gutschriften, len(ergebnis.uebersprungen)) == (0, [], 2)
    assert session.execute(select(Buchung)).first() is None


def test_bewirtung_wird_entwurf_mit_anteil(admin, session):
    teile = [("47.25", "6640", "Bewirtungskosten"), ("20.25", "6644", "Nicht abzugsfähig")]
    ergebnis = importiere_archiv(archiv(beleg("B1", "67.50", teile=teile)), admin.id)
    assert ergebnis.entwuerfe == 1
    buchung = session.execute(select(Buchung)).scalar_one()
    assert (buchung.betrag_cent, buchung.betrieblich_prozent) == (6750, 70)


def test_vorschau_speichert_nichts(admin, session):
    ergebnis = importiere_archiv(archiv(beleg("A1", "119.00")), admin.id, pruefen=True)
    assert ergebnis.festgeschrieben == 1 and ergebnis.kontakte_neu == 1
    assert session.execute(select(Buchung)).first() is None
    assert session.execute(select(Beleg)).first() is None
    assert session.execute(select(Kontakt)).first() is None


def test_zweiter_import_und_ueberlappung_ohne_doppelte(admin, session):
    daten = archiv(beleg("A1", "119.00"), beleg("A2", "20.00"))
    importiere_archiv(daten, admin.id)
    nochmal = importiere_archiv(daten, admin.id)
    assert nochmal.neu == 0 and len(nochmal.uebersprungen) == 2
    assert len(session.execute(select(Buchung)).all()) == 2
    # Monatsexport mit gleichem Beleg in einer zweiten Datei desselben Laufs
    bekannt: set = set()
    a = importiere_archiv(archiv(beleg("N1", "5.00")), admin.id, bekannt=bekannt)
    b = importiere_archiv(archiv(beleg("N1", "5.00")), admin.id, bekannt=bekannt)
    assert (a.neu, b.neu, len(b.uebersprungen)) == (1, 0, 1)


def test_kaputtes_archiv(admin):
    assert "keine ZIP" in importiere_archiv(b"nope", admin.id).probleme[0]
    assert (
        "document.xml fehlt"
        in importiere_archiv(archiv(beleg("A1", "1.00"), ohne_verzeichnis=True), admin.id).probleme[
            0
        ]
    )
    with pytest.raises(ArchivUngueltig):
        lies_archiv(b"PK\x05\x06" + b"\0" * 18 + b"x")


def test_oberflaeche_vorschau_dann_import(angemeldet, session):
    daten = archiv(beleg("A1", "119.00"))
    antwort = angemeldet.post(
        "/import/archiv",
        data={"dateien": (io.BytesIO(daten), "export.zip")},
        content_type="multipart/form-data",
    )
    seite = antwort.get_data(as_text=True)
    assert "würden angelegt" in seite
    assert session.execute(select(Buchung)).first() is None
    token = seite.split('name="token" value="')[1].split('"')[0]
    antwort = angemeldet.post("/import/archiv", data={"token": token, "aktion": "importieren"})
    assert "Buchungen angelegt" in antwort.get_data(as_text=True)
    assert len(session.execute(select(Buchung)).all()) == 1


def test_nur_mit_recht_buchen(client, admin, session):
    from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

    neuer_nutzer(session, "mitarbeiter@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "mitarbeiter@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/import/archiv").status_code == 403


def test_import_export_seite_mit_anleitung(angemeldet):
    seite = angemeldet.get("/einstellungen/import-export").get_data(as_text=True)
    assert "Anleitung: Umzug von Lexware Office" in seite
    assert "Belegarchiv importieren" in seite
    assert "Gesamtexport herunterladen" in seite
    assert ">Import/Export</a>" in angemeldet.get("/einstellungen/firma").get_data(as_text=True)


def test_import_export_braucht_einstellungsrecht(client, admin, session):
    from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

    neuer_nutzer(session, "mitarbeiter@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "mitarbeiter@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/einstellungen/import-export").status_code == 403


KOPF = (
    "RG-Datum;RG-Nr.;Steuer;Steuerbetrag;Gesamtbetrag;Währung;Kategorie;bezahlt am;"
    "Lieferantennummer;Firmenname\n"
)


def liste(*zeilen):
    text = KOPF + "".join(
        f"{d};{nr};Keine;0,00;{betrag};EUR;Waren;{bezahlt};70001;Muster Verlag\n"
        for d, nr, betrag, bezahlt in zeilen
    )
    return ("\ufeff" + text).encode("utf-8")


def test_zahlungen_aus_liste(admin, session):
    from app.services.archivimport import uebernehme_zahlungen

    importiere_archiv(
        archiv(
            beleg("Z1", "119.00", datum="2025-03-01"),
            beleg("Z2", "20.00", datum="2025-03-02"),
            beleg("Z3", "30.00", datum="2025-03-03"),
        ),
        admin.id,
    )
    csv = liste(
        ("01.03.2025", "Z1", "119,00", "15.03.2025"),
        ("02.03.2025", "Z2-", "20,00", "16.03.2025"),  # Nummer anders geschrieben, Rest eindeutig
        ("09.09.2025", "X9", "1,00", "10.09.2025"),  # gibt es nicht
    )
    vorschau = uebernehme_zahlungen(csv, admin.id, pruefen=True)
    assert (vorschau.erfasst, len(vorschau.ohne_treffer)) == (2, 1)
    assert all(b.zahlungen == [] for b in session.execute(select(Buchung)).scalars())
    ergebnis = uebernehme_zahlungen(csv, admin.id)
    assert (ergebnis.erfasst, len(ergebnis.ohne_treffer)) == (2, 1)
    stand = {b.belegnummer: b for b in session.execute(select(Buchung)).scalars()}
    assert stand["Z1"].zahlstatus == "bezahlt"
    assert stand["Z1"].zahlungen[0].datum.isoformat() == "2025-03-15"
    assert stand["Z2"].zahlstatus == "bezahlt"
    assert stand["Z3"].zahlstatus == "offen"
    # Wiederholung ändert nichts
    nochmal = uebernehme_zahlungen(csv, admin.id)
    assert nochmal.erfasst == 0


def test_zahlung_zu_entwurf_wird_gemeldet(admin, session):
    from app.services.archivimport import uebernehme_zahlungen

    importiere_archiv(archiv(beleg("D1", "10.00", konto="9999", datum="2025-03-01")), admin.id)
    ergebnis = uebernehme_zahlungen(liste(("01.03.2025", "D1", "10,00", "05.03.2025")), admin.id)
    assert (ergebnis.erfasst, len(ergebnis.entwuerfe), ergebnis.ohne_treffer) == (0, 1, [])


def test_zahlungsliste_mehrdeutig_und_ungueltig(admin, session):
    from app.services.archivimport import ist_zahlungsliste, uebernehme_zahlungen

    importiere_archiv(archiv(beleg("M1", "10.00", datum="2025-03-01")), admin.id)
    zwei = liste(
        ("01.03.2025", "M1", "10,00", "05.03.2025"), ("01.03.2025", "M1", "10,00", "06.03.2025")
    )
    assert len(uebernehme_zahlungen(zwei, admin.id).mehrdeutig) == 2
    assert not ist_zahlungsliste(b"a;b\n1;2\n")
    zukunft = liste(("01.03.2025", "M1", "10,00", "01.01.2099"))
    ergebnis = uebernehme_zahlungen(zukunft, admin.id)
    assert ergebnis.erfasst == 0 and "Zukunft" in ergebnis.probleme[0]


def test_oberflaeche_archiv_und_liste_zusammen(angemeldet, session):
    import io
    import zipfile

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("Export_RE.csv", liste(("01.03.2025", "U1", "119,00", "15.03.2025")))
    antwort = angemeldet.post(
        "/import/archiv",
        data={
            "dateien": [
                (io.BytesIO(puffer.getvalue()), "CSV-Export.zip"),
                (io.BytesIO(archiv(beleg("U1", "119.00", datum="2025-03-01"))), "archiv.zip"),
            ]
        },
        content_type="multipart/form-data",
    )
    seite = antwort.get_data(as_text=True)
    assert "Zahlungen würden erfasst" in seite and "Buchungen würden angelegt" in seite
    token = seite.split('name="token" value="')[1].split('"')[0]
    angemeldet.post("/import/archiv", data={"token": token, "aktion": "importieren"})
    buchung = session.execute(select(Buchung)).scalar_one()
    assert buchung.zahlstatus == "bezahlt"


KOPF_AUSGANG = (
    "RG-Datum;Liefer-Datum;RG-Nr.;Steuer;Steuerbetrag;Gesamtbetrag;Währung;Kategorie;"
    "bezahlt am;Fällig;Kundenummer;Firmenname\n"
)


def ausgangsliste(*zeilen):
    text = KOPF_AUSGANG + "".join(
        f"{d};{d};{nr};Keine;0,00;{betrag};EUR;Erlöse;{bezahlt};{d};10000;Muster Cafe\n"
        for d, nr, betrag, bezahlt in zeilen
    )
    return ("\ufeff" + text).encode("utf-8")


def test_zahlungen_der_einnahmen_aus_ausgangsliste(admin, session):
    import io
    import zipfile

    from app.services.archivimport import (
        uebernehme_zahlungen,
        zahlungslisten_im_zip,
    )

    importiere_archiv(
        archiv(
            beleg("RE5", "400.00", art="einnahme", konto="4185", datum="2026-01-05"),
            beleg("RE6", "50.00", art="einnahme", konto="4185", datum="2026-01-06"),
            beleg("EK1", "9.00", datum="2026-01-05"),
        ),
        admin.id,
    )
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("Export_RA.csv", ausgangsliste(("05.01.2026", "RE5", "400,00", "10.01.2026")))
        z.writestr("Export_RE.csv", liste(("05.01.2026", "EK1", "9,00", "07.01.2026")))
        z.writestr("Notiz.txt", "x")
    listen = zahlungslisten_im_zip(puffer.getvalue())
    assert len(listen) == 2
    ergebnisse = [uebernehme_zahlungen(daten, admin.id) for daten in listen]
    assert [(e.liste, e.erfasst) for e in ergebnisse] == [("Einnahmen", 1), ("Ausgaben", 1)]
    stand = {b.belegnummer: b.zahlstatus for b in session.execute(select(Buchung)).scalars()}
    assert stand == {"RE5": "bezahlt", "RE6": "offen", "EK1": "bezahlt"}
