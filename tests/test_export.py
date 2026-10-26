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


# ---------- Prüfsummen (SHA256SUMS) ----------


def archiv_neu(zip_: zipfile.ZipFile, ersetze: dict[str, bytes] | None = None) -> bytes:
    """Das Archiv mit einzelnen geänderten Dateien neu packen (simuliert eine Manipulation)."""
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as neu:
        for name in zip_.namelist():
            neu.writestr(name, (ersetze or {}).get(name, zip_.read(name)))
        for name, inhalt in (ersetze or {}).items():
            if name not in zip_.namelist():
                neu.writestr(name, inhalt)
    return puffer.getvalue()


def test_jahresexport_hat_pruefsummen_fuer_jede_datei(angemeldet, daten):
    import hashlib

    zip_ = oeffnen(angemeldet.get(f"/auswertung/export.zip?jahr={HEUTE.year}"))
    summen = {}
    for zeile in zip_.read("SHA256SUMS").decode().splitlines():
        summe, _, name = zeile.partition("  ")
        summen[name] = summe
    erwartet = set(zip_.namelist()) - {"SHA256SUMS"}
    assert set(summen) == erwartet
    for name, summe in summen.items():
        assert hashlib.sha256(zip_.read(name)).hexdigest() == summe
    assert (
        "PRUEFEN.txt" in zip_.namelist()
        and "sha256sum -c SHA256SUMS" in zip_.read("PRUEFEN.txt").decode()
    )
    assert f"Rechnungen-{HEUTE.year}.csv" in zip_.namelist()
    uebersicht = zip_.read(f"Rechnungen-{HEUTE.year}.csv").decode("utf-8-sig")
    assert daten.nummer in uebersicht and daten.pdf_sha256 in uebersicht


@pytest.mark.parametrize("adresse", ["/auswertung/export.zip", "/auswertung/gesamtexport.zip"])
def test_unveraendertes_archiv_besteht_die_pruefung(angemeldet, daten, adresse):
    from app.services.export import pruefe_archiv

    antwort = angemeldet.get(adresse)
    assert pruefe_archiv(antwort.data) == []


def test_pruefung_findet_veraenderte_fehlende_und_hinzugefuegte_dateien(angemeldet, daten):
    from app.services.export import pruefe_archiv

    zip_ = oeffnen(angemeldet.get(f"/auswertung/export.zip?jahr={HEUTE.year}"))
    rechnung_pdf = f"rechnungen/{daten.nummer}.pdf"
    geaendert = archiv_neu(zip_, {rechnung_pdf: b"%PDF-gefaelscht"})
    assert any(
        "Prüfsumme stimmt nicht" in p and rechnung_pdf in p for p in pruefe_archiv(geaendert)
    )
    dazu = archiv_neu(zip_, {"zusaetzlich.txt": b"neu"})
    assert any("zusaetzlich.txt" in p and "steht nicht" in p for p in pruefe_archiv(dazu))
    # Datei entfernt
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as ohne:
        for name in zip_.namelist():
            if name != rechnung_pdf:
                ohne.writestr(name, zip_.read(name))
    assert any("fehlt im Archiv" in p for p in pruefe_archiv(puffer.getvalue()))
    # Summenliste fehlt oder keine ZIP-Datei
    assert pruefe_archiv(b"kein zip") == ["Das ist keine ZIP-Datei."]
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as leer:
        leer.writestr("a.txt", "x")
    assert "SHA256SUMS fehlt" in pruefe_archiv(puffer.getvalue())[0]


def test_befehl_export_pruefen(app, angemeldet, daten, tmp_path):
    ok = tmp_path / "ok.zip"
    ok.write_bytes(angemeldet.get("/auswertung/gesamtexport.zip").data)
    ergebnis = app.test_cli_runner().invoke(args=["export-pruefen", str(ok)])
    assert ergebnis.exit_code == 0 and "Alle Prüfsummen stimmen" in ergebnis.output
    kaputt = tmp_path / "kaputt.zip"
    zip_ = zipfile.ZipFile(ok)
    kaputt.write_bytes(archiv_neu(zip_, {"daten/gewerbe.csv": b"geaendert"}))
    ergebnis = app.test_cli_runner().invoke(args=["export-pruefen", str(kaputt)])
    assert ergebnis.exit_code == 1 and "daten/gewerbe.csv" in ergebnis.output
