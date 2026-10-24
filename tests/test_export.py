import io
import zipfile
from datetime import date

import pytest
from sqlalchemy import select

from app.models import Protokoll
from app.services.zahlungen import erfasse_zahlung
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_belege import formular, hochladen, text_pdf
from tests.test_belegerkennung import TANKBELEG
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()


@pytest.fixture
def daten(angemeldet, rechnung, admin, session):  # noqa: F811
    erfasse_zahlung(
        rechnung,
        datum=HEUTE,
        betrag_cent=15220,
        zahlungsart="ueberweisung",
        angekommen_cent=None,
        notiz=None,
        nutzer_id=admin.id,
    )
    hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    from app.models import Beleg

    beleg = session.execute(select(Beleg)).scalar_one()
    angemeldet.post(
        f"/belege/{beleg.id}",
        data=formular(
            session,
            belegdatum=HEUTE.isoformat(),
            bereits_bezahlt="y",
            bezahlt_am=HEUTE.isoformat(),
        ),
    )
    return rechnung


def oeffnen(antwort) -> zipfile.ZipFile:
    assert antwort.mimetype == "application/zip"
    return zipfile.ZipFile(io.BytesIO(antwort.data))


def test_steuerberater_zip(angemeldet, daten, session):
    zip_ = oeffnen(angemeldet.get(f"/auswertung/export.zip?jahr={HEUTE.year}"))
    namen = set(zip_.namelist())
    assert {
        f"EUER-{HEUTE.year}.pdf",
        f"EUER-{HEUTE.year}.csv",
        f"Zahlungen-{HEUTE.year}.csv",
        f"rechnungen/{daten.nummer}.pdf",
        "belege/Index.csv",
        "LIESMICH.txt",
    } <= namen
    belegdateien = [n for n in namen if n.startswith("belege/") and n.endswith(".pdf")]
    assert len(belegdateien) == 1  # IDs hängen von der Testreihenfolge ab
    zahlungen = zip_.read(f"Zahlungen-{HEUTE.year}.csv").decode("utf-8-sig")
    assert f";Einnahme;{daten.nummer};" in zahlungen
    assert (
        f"Muster Tankstelle GmbH;Fahrzeugkosten;81,17;100;81,17;karte;{belegdateien[0]}"
        in zahlungen
    )
    assert zip_.read(f"rechnungen/{daten.nummer}.pdf").startswith(b"%PDF")
    assert "tanken.pdf" in zip_.read("belege/Index.csv").decode("utf-8-sig")
    euer = zip_.read(f"EUER-{HEUTE.year}.csv").decode("utf-8-sig")
    assert ";;Gewinn/Verlust;71,03" in euer
    aktionen = session.execute(select(Protokoll.aktion)).scalars().all()
    assert "export_steuerberater" in aktionen


def test_leeres_jahr(angemeldet):
    zip_ = oeffnen(angemeldet.get("/auswertung/export.zip?jahr=2025"))
    assert "EUER-2025.pdf" in zip_.namelist()


def test_gesamtexport(angemeldet, daten, session):
    zip_ = oeffnen(angemeldet.get("/auswertung/gesamtexport.zip"))
    namen = zip_.namelist()
    for tabelle in ("gewerbe", "nutzer", "rechnung", "zahlung", "beleg", "buchung", "protokoll"):
        assert f"daten/{tabelle}.csv" in namen
    nutzer = zip_.read("daten/nutzer.csv").decode("utf-8-sig")
    assert "passwort_hash" not in nutzer and "argon2" not in nutzer
    assert sum(1 for n in namen if n.startswith("ablage/")) >= 2  # Rechnungs-PDF und Beleg
    assert "export_gesamt" in session.execute(select(Protokoll.aktion)).scalars().all()


@pytest.mark.parametrize(
    ("rolle", "export", "gesamt"),
    [("steuerberater", 200, 403), ("buchhalter", 200, 403), ("mitarbeiter", 403, 403)],
)
def test_rechte(client, admin, session, rolle, export, gesamt):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/auswertung/export.zip").status_code == export
    assert client.get("/auswertung/gesamtexport.zip").status_code == gesamt


def test_knopf_in_einstellungen(angemeldet):
    assert "Gesamtexport herunterladen" in angemeldet.get("/einstellungen/firma").get_data(
        as_text=True
    )
