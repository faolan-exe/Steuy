import io
import zipfile
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.domain.datev import (
    ANZAHL_SPALTEN,
    DatevUngueltig,
    Kopf,
    Posten,
    buchungsstapel,
    buchungszeilen,
    konto,
    kopfzeile,
    pruefe_kopf,
)
from app.models import Protokoll
from app.services.artikel import lege_artikel_an
from app.services.buchungen import storniere
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_artikel import DJ
from tests.test_euer import ausgabe, zahlen
from tests.test_kontakte import FIRMA, anlegen
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()
KOPF = Kopf(2025, "SKR03", 1001, 1, datetime(2026, 1, 5, 9, 30))


def posten(**mehr):
    daten = {
        "art": "einnahme",
        "datum": date(2025, 3, 14),
        "betrag_cent": 15220,
        "kategorie": "Rechnung",
        "zahlungsart": "ueberweisung",
        "belegfeld": "RE0001",
        "text": "Café Sonnenschein",
    }
    daten.update(mehr)
    return Posten(**daten)


# ---------- Domain ----------


def test_kopfzeile():
    kopf = kopfzeile(KOPF)
    assert kopf[:5] == ['"EXTF"', "700", "21", '"Buchungsstapel"', "13"]
    assert kopf[5] == "20260105093000000"
    assert kopf[10:16] == ["1001", "1", "20250101", "4", "20250101", "20251231"]
    assert kopf[21] == '"EUR"' and kopf[26] == '"03"'
    assert kopfzeile(Kopf(2025, "SKR04", 1001, 1, KOPF.erstellt))[26] == '"04"'


def test_einnahme_bank_an_erloes():
    (zeile,) = buchungszeilen(posten(), "SKR03")
    assert len(zeile) == ANZAHL_SPALTEN
    assert zeile[:3] == ["152,20", '"S"', '"EUR"']
    assert zeile[6:8] == ["1200", "8195"]
    assert zeile[9:11] == ["1403", '"RE0001"']
    assert zeile[13] == '"Café Sonnenschein"'
    (zeile,) = buchungszeilen(posten(zahlungsart="bar"), "SKR04")
    assert zeile[6:8] == ["1600", "4185"]


def test_ausgabe_aufwand_an_bank_und_storno():
    (zeile,) = buchungszeilen(posten(art="ausgabe", kategorie="Werbung"), "SKR03")
    assert zeile[:2] == ["152,20", '"S"'] and zeile[6:8] == ["4600", "1200"]
    (zeile,) = buchungszeilen(
        posten(art="ausgabe", kategorie="Werbung", betrag_cent=-15220), "SKR03"
    )
    assert zeile[:2] == ["152,20", '"H"'] and zeile[6:8] == ["4600", "1200"]


def test_privatanteil_auf_privatkonto():
    zeilen = buchungszeilen(
        posten(
            art="ausgabe",
            kategorie="Telefon und Internet",
            betrag_cent=4001,
            betrieblich_prozent=50,
        ),
        "SKR04",
    )
    assert [(z[0], z[6], z[7]) for z in zeilen] == [
        ("20,00", "6805", "1800"),
        ("20,01", "2100", "1800"),
    ]
    assert zeilen[1][13].endswith('(privat)"')
    # Storno hebt beides exakt auf
    storno = buchungszeilen(
        posten(
            art="ausgabe",
            kategorie="Telefon und Internet",
            betrag_cent=-4001,
            betrieblich_prozent=50,
        ),
        "SKR04",
    )
    assert [(z[0], z[1]) for z in storno] == [("20,00", '"H"'), ("20,01", '"H"')]


def test_unbekannte_kategorie_auf_sonstige():
    assert konto("Exotisch", "ausgabe", "SKR03") == 4900
    assert konto(None, "einnahme", "SKR04") == 4830


def test_datei_kodierung_und_jahr():
    inhalt = buchungsstapel(KOPF, [posten(text='Müller "GmbH"\nKöln')])
    assert inhalt.endswith(b"\r\n") and inhalt.count(b"\r\n") == 3
    text = inhalt.decode("cp1252")
    assert "\"Müller 'GmbH' Köln\"" in text
    with pytest.raises(DatevUngueltig, match="Wirtschaftsjahr"):
        buchungsstapel(KOPF, [posten(datum=date(2026, 1, 1))])


@pytest.mark.parametrize(
    ("rahmen", "berater", "mandant"),
    [("SKR99", 1001, 1), ("SKR03", 1000, 1), ("SKR03", 1001, 0), ("SKR03", 1001, 100000)],
)
def test_kopf_pruefung(rahmen, berater, mandant):
    with pytest.raises(DatevUngueltig):
        pruefe_kopf(rahmen, berater, mandant)


# ---------- Export ----------


def herunterladen(client, **daten):
    formular = {"kontenrahmen": "SKR03", "beraternummer": "1001", "mandantennummer": "1"}
    formular.update(daten)
    antwort = client.post("/auswertung/wechsel", data=formular)
    assert antwort.status_code == 200, antwort.get_data(as_text=True)[:300]
    return zipfile.ZipFile(io.BytesIO(antwort.data))


def test_wechsel_export(angemeldet, rechnung, admin, session):  # noqa: F811
    zahlen(rechnung, admin, 15220)
    storniere(ausgabe(session, admin, "Werbung", 5000, datum=date(HEUTE.year - 1, 6, 1)), admin.id)
    anlegen(FIRMA, admin, typ="beides")
    lege_artikel_an({**DJ, "preis_cent": 6500}, admin.id)

    zip_ = herunterladen(angemeldet)
    namen = set(zip_.namelist())
    assert {
        f"DATEV/EXTF_Buchungsstapel_{HEUTE.year}.csv",
        f"DATEV/EXTF_Buchungsstapel_{HEUTE.year - 1}.csv",
        "Stammdaten/Kunden.csv",
        "Stammdaten/Lieferanten.csv",
        "Stammdaten/Artikel.csv",
        "LIESMICH.txt",
    } <= namen

    aktuell = zip_.read(f"DATEV/EXTF_Buchungsstapel_{HEUTE.year}.csv").decode("cp1252")
    zeilen = aktuell.split("\r\n")
    assert zeilen[0].startswith('"EXTF";700;21;"Buchungsstapel"')
    assert zeilen[2].startswith('152,20;"S";"EUR";;;;1200;8195;')
    # Ausgabe und Storno im Vorjahr: gleiche Konten, Soll und Haben
    vorjahr = zip_.read(f"DATEV/EXTF_Buchungsstapel_{HEUTE.year - 1}.csv").decode("cp1252")
    buchungen = vorjahr.split("\r\n")[2:-1]
    assert [z.split(";")[:2] for z in buchungen] == [["50,00", '"S"'], ["50,00", '"H"']]
    assert all(z.split(";")[6:8] == ["4600", "1200"] for z in buchungen)

    kunden = zip_.read("Stammdaten/Kunden.csv").decode("utf-8-sig")
    assert kunden.startswith("Kundennummer;Firmenname;")
    assert "10000;Café Sonnenschein;" in kunden
    assert "Café Sonnenschein" in zip_.read("Stammdaten/Lieferanten.csv").decode("utf-8-sig")
    artikel = zip_.read("Stammdaten/Artikel.csv").decode("utf-8-sig")
    assert ";Dienstleistung;Auftritt pro Stunde;" in artikel and ";65,00;" in artikel

    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "export_wechsel")
    ).scalar_one()
    assert eintrag.details["jahre"] == [HEUTE.year - 1, HEUTE.year]


def test_skr04_und_leerer_bestand(angemeldet):
    zip_ = herunterladen(angemeldet, kontenrahmen="SKR04")
    assert not any(n.startswith("DATEV/") for n in zip_.namelist())
    assert "SKR04" in zip_.read("LIESMICH.txt").decode()


def test_formular_prueft(angemeldet):
    seite = angemeldet.post(
        "/auswertung/wechsel",
        data={"kontenrahmen": "SKR03", "beraternummer": "12", "mandantennummer": "1"},
    ).get_data(as_text=True)
    assert "Zwischen 1001 und 9999999." in seite


def test_seite_und_links(angemeldet):
    assert "Daten für andere Software" in angemeldet.get("/auswertung/wechsel").get_data(
        as_text=True
    )
    assert "Wechsel-Export" in angemeldet.get("/auswertung").get_data(as_text=True)


@pytest.mark.parametrize(("rolle", "status"), [("mitarbeiter", 403), ("steuerberater", 200)])
def test_rechte(client, admin, session, rolle, status):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/auswertung/wechsel").status_code == status
