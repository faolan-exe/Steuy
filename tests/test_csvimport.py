import base64
import io

import pytest
from sqlalchemy import select

from app.domain.csvimport import CsvUngueltig, artikel_aus, kontakt_aus, lies, vorschlag
from app.models import Artikel, Kontakt, Protokoll
from app.services.csvimport import importiere_artikel, importiere_kontakte
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

KONTAKTE = (
    "Kundennummer;Firmenname;Vorname;Nachname;Straße;PLZ;Ort;Land;E-Mail;Telefon\n"
    "10007;Café Sonnenschein;;;Markt 5;50667;Köln;Deutschland;hallo@cafe.example;0221 1\n"
    "10008;;Jonas;Weber;Hafen 1;20095;Hamburg;Deutschland;jonas@example.de;\n"
    ";;;;;;;;;\n"
    "10009;;Nur;;Weg 2;12345;Berlin;Deutschland;;\n"
)


# ---------- Domain ----------


def test_lesen_utf8_semikolon_und_leere_zeilen():
    kopf, zeilen = lies(KONTAKTE.encode("utf-8-sig"))
    assert kopf[1] == "Firmenname" and len(zeilen) == 4  # leere Zeile bleibt für die Nummerierung


def test_lesen_windows_1252_und_komma():
    inhalt = 'Bezeichnung,Preis\nKaffee groß,"3,50"\n'.encode("cp1252")
    kopf, zeilen = lies(inhalt)
    assert kopf == ["Bezeichnung", "Preis"] and zeilen == [["Kaffee groß", "3,50"]]


@pytest.mark.parametrize(
    ("inhalt", "meldung"),
    [(b"", "leer"), (b"nur eine spalte\nwert\n", "Keine Spalten"), (b"a;b\n", "keine Datenzeilen")],
)
def test_ungueltige_dateien(inhalt, meldung):
    with pytest.raises(CsvUngueltig, match=meldung):
        lies(inhalt)


def test_vorschlag_erkennt_uebliche_spaltennamen():
    kopf = [
        "Kunden-Nr.",
        "Firma",
        "Vorname",
        "Name",
        "Straße und Hausnummer",
        "Postleitzahl",
        "Stadt",
        "E-Mail-Adresse",
        "Bemerkung",
    ]
    z = vorschlag("kontakte", kopf)
    assert (z["kundennummer"], z["firmenname"], z["nachname"], z["strasse"]) == (0, 1, 3, 4)
    assert (z["plz"], z["ort"], z["email"], z["notiz"]) == (5, 6, 7, 8)
    assert z["telefon"] is None


def test_preis_wird_nicht_aus_netto_geraten():
    assert vorschlag("artikel", ["Name", "Netto", "Brutto"])["preis"] is None


def test_kontakt_und_artikel_aus_zeile():
    z = {"firmenname": None, "nachname": 1, "vorname": 0, "kundennummer": 2, "email": 3}
    daten = kontakt_aus(["Mia", "Muster", "123", "mia@example.de"], z, "kunde")
    assert daten["art"] == "person" and daten["kundennummer"] == 123
    with pytest.raises(CsvUngueltig, match="Weder Firmenname"):
        kontakt_aus(["", "", "", ""], z, "kunde")
    a = artikel_aus(
        ["Beratung", "1.234,50", "Dienstleistung"], {"bezeichnung": 0, "preis": 1, "typ": 2}
    )
    assert (a["preis_cent"], a["typ"], a["einheit"]) == (123450, "service", "Stunde")
    with pytest.raises(CsvUngueltig, match="Preis"):
        artikel_aus(["Kaffee", "drei Euro"], {"bezeichnung": 0, "preis": 1})


# ---------- Service ----------


def test_kontakte_importieren_mit_nummern_und_dubletten(admin, session):
    kopf, zeilen = lies(KONTAKTE.encode())
    zuordnung = vorschlag("kontakte", kopf)
    vorschau = importiere_kontakte(zeilen, zuordnung, "kunde", admin.id, pruefen=True)
    assert vorschau.neu == 2 and len(vorschau.fehler) == 1
    assert session.execute(select(Kontakt)).first() is None  # Prüfen speichert nichts

    ergebnis = importiere_kontakte(zeilen, zuordnung, "kunde", admin.id)
    assert ergebnis.neu == 2
    cafe = session.execute(select(Kontakt).where(Kontakt.art == "firma")).scalar_one()
    assert cafe.kundennummer == 10007 and cafe.ort == "Köln"
    # Gleiche Datei noch einmal: alles doppelt, nichts neu
    nochmal = importiere_kontakte(zeilen, zuordnung, "kunde", admin.id)
    assert nochmal.neu == 0 and len(nochmal.doppelt) == 2
    eintrag = (
        session.execute(select(Protokoll).where(Protokoll.aktion == "csv_import")).scalars().first()
    )
    assert eintrag.details["neu"] == 2


def test_belegte_nummer_bekommt_neue(admin, session):
    from app.services.kontakte import lege_kontakt_an

    vorhanden = lege_kontakt_an({"art": "person", "nachname": "Alt", "typ": "kunde"}, admin.id)
    datei = f"Kundennummer;Nachname\n{vorhanden.kundennummer};Neu\n".encode()
    kopf, zeilen = lies(datei)
    ergebnis = importiere_kontakte(zeilen, vorschlag("kontakte", kopf), "kunde", admin.id)
    assert ergebnis.neu == 1
    neu = session.execute(select(Kontakt).where(Kontakt.nachname == "Neu")).scalar_one()
    assert neu.kundennummer != vorhanden.kundennummer


def test_rundreise_mit_eigenem_wechsel_export(angemeldet, admin, session):
    """Kunden.csv aus dem Wechsel-Export lässt sich ohne Nacharbeit wieder einlesen."""
    import zipfile

    from app.services.kontakte import lege_kontakt_an

    lege_kontakt_an(
        {
            "art": "firma",
            "firmenname": "Druckerei Blau",
            "typ": "kunde",
            "ort": "Bonn",
            "email": "info@blau.example",
        },
        admin.id,
    )
    antwort = angemeldet.post(
        "/auswertung/wechsel",
        data={"kontenrahmen": "SKR03", "beraternummer": "1001", "mandantennummer": "1"},
    )
    kunden = zipfile.ZipFile(io.BytesIO(antwort.data)).read("Stammdaten/Kunden.csv")
    session.query(Kontakt).delete()
    session.commit()
    kopf, zeilen = lies(kunden)
    ergebnis = importiere_kontakte(zeilen, vorschlag("kontakte", kopf), "kunde", admin.id)
    assert ergebnis.neu == 1 and not ergebnis.fehler
    blau = session.execute(select(Kontakt)).scalar_one()
    assert (blau.firmenname, blau.ort, blau.email, blau.kundennummer) == (
        "Druckerei Blau",
        "Bonn",
        "info@blau.example",
        10000,
    )


def test_artikel_importieren(admin, session):
    datei = (
        b"Artikelnummer;Bezeichnung;Preis;Einheit\n"
        b"T-1;Tasse;12,50;\nT-1;Doppelt;1,00;\n;Ohne Preis;;\n"
    )
    kopf, zeilen = lies(datei)
    ergebnis = importiere_artikel(zeilen, vorschlag("artikel", kopf), admin.id)
    assert ergebnis.neu == 1 and len(ergebnis.doppelt) == 1 and len(ergebnis.fehler) == 1
    tasse = session.execute(select(Artikel)).scalar_one()
    assert (tasse.preis_cent, tasse.einheit, tasse.typ) == (1250, "Stück", "produkt")


# ---------- Oberfläche ----------


def test_ablauf_ueber_oberflaeche(angemeldet, session):
    seite = angemeldet.post(
        "/import/zuordnen",
        data={
            "art": "kontakte",
            "typ": "lieferant",
            "datei": (io.BytesIO(KONTAKTE.encode()), "kunden.csv"),
        },
        content_type="multipart/form-data",
    ).get_data(as_text=True)
    assert "Welche Spalte gehört wohin?" in seite and "Café Sonnenschein" in seite
    assert 'name="feld_firmenname"' in seite

    formular = {
        "art": "kontakte",
        "typ": "lieferant",
        "daten": base64.b64encode(KONTAKTE.encode()).decode(),
        "feld_firmenname": "1",
        "feld_nachname": "3",
        "feld_ort": "6",
        "aktion": "pruefen",
    }
    seite = angemeldet.post("/import/ausfuehren", data=formular).get_data(as_text=True)
    assert "würden angelegt" in seite and "Zeile 5: Weder Firmenname" in seite
    assert session.execute(select(Kontakt)).first() is None

    seite = angemeldet.post(
        "/import/ausfuehren", data=formular | {"aktion": "importieren"}
    ).get_data(as_text=True)
    assert "Import fertig" in seite
    kontakte = session.execute(select(Kontakt)).scalars().all()
    assert len(kontakte) == 2 and all(k.ist_lieferant and not k.ist_kunde for k in kontakte)


def test_pflichtfelder_artikel_verhindern_import(angemeldet, session):
    daten = base64.b64encode(b"Name;Netto\nTasse;10,00\n").decode()
    seite = angemeldet.post(
        "/import/ausfuehren",
        data={"art": "artikel", "daten": daten, "feld_bezeichnung": "0", "aktion": "importieren"},
    ).get_data(as_text=True)
    assert "Bitte noch zuordnen: Preis EUR" in seite
    assert session.execute(select(Artikel)).first() is None


def test_kaputte_daten(angemeldet):
    antwort = angemeldet.post("/import/ausfuehren", data={"daten": "%%%", "aktion": "importieren"})
    assert antwort.status_code == 302


def test_links_in_listen(angemeldet):
    assert "/import?art=kontakte" in angemeldet.get("/kontakte").get_data(as_text=True)
    assert "/import?art=artikel" in angemeldet.get("/artikel").get_data(as_text=True)


@pytest.mark.parametrize(("rolle", "status"), [("steuerberater", 403), ("mitarbeiter", 200)])
def test_rechte(client, admin, session, rolle, status):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/import").status_code == status
