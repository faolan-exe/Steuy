import io
import os
import time

import pytest
from PIL import Image
from sqlalchemy import func, select
from weasyprint import HTML

from app.domain.rollen import Rolle
from app.models import Beleg, Protokoll
from app.services import scaneingang
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT, neuer_nutzer


def pdf(text: str = "Beleg") -> bytes:
    return HTML(string=f"<p>{text}</p>").write_pdf()


def bild(format: str, farbe="white") -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (40, 30), farbe).save(puffer, format=format)
    return puffer.getvalue()


@pytest.fixture
def scan(app, tmp_path, admin):
    """Ein Scan-Ordner in tmp_path, Scan-Eingang eingeschaltet, Texterkennung aus (schnell)."""
    schluessel = ("SCAN_VERZEICHNIS", "FREIGABE_VERZEICHNIS", "TEXTERKENNUNG")
    alt = {k: app.config[k] for k in schluessel}
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "scan-eingang")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "freigabe")
    app.config["TEXTERKENNUNG"] = False
    with app.app_context():
        scaneingang.setze_aktiv(True, admin.id)
        yield tmp_path / "scan-eingang"
    app.config.update(alt)


def ablegen(ordner, name, inhalt, alter=60):
    datei = ordner / name
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_bytes(inhalt)
    jetzt = time.time() - alter
    os.utime(datei, (jetzt, jetzt))
    return datei


def anzahl(session, modell):
    return session.scalar(select(func.count()).select_from(modell))


def test_einschalten_legt_den_ordner_an(app, session, admin, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "neu" / "scan")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "freigabe")
    with app.app_context():
        assert not scaneingang.ist_aktiv()
        scaneingang.setze_aktiv(True, admin.id)
        assert scaneingang.ist_aktiv()
        assert (tmp_path / "neu" / "scan").is_dir()
        scaneingang.setze_aktiv(False, admin.id)
        assert not scaneingang.ist_aktiv()


def test_ausgeschaltet_passiert_nichts(app, session, admin, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "scan")
    datei = ablegen(tmp_path / "scan", "a.pdf", pdf())
    with app.app_context():
        ergebnis = scaneingang.pruefe_ordner()
    assert ergebnis.uebersprungen
    assert datei.exists()
    assert anzahl(session, Beleg) == 0


@pytest.mark.parametrize(
    "name,inhalt",
    [
        ("rechnung.pdf", pdf("A")),
        ("foto.jpg", bild("JPEG")),
        ("Foto.JPEG", bild("JPEG", "red")),
        ("scan.png", bild("PNG")),
    ],
)
def test_uebernimmt_pdf_jpg_und_png(app, session, scan, name, inhalt):
    ablegen(scan, name, inhalt)
    with app.app_context():
        ergebnis = scaneingang.pruefe_ordner()
    assert ergebnis.importiert == [name]
    beleg = session.scalars(select(Beleg)).one()
    assert beleg.dateiname == name and not beleg.verworfen
    # Original ist weg aus dem Eingang und liegt unter verarbeitet/
    assert not (scan / name).exists()
    assert len(list((scan / "verarbeitet").rglob(name))) == 1


def test_beleg_ist_in_der_ablage_und_im_protokoll(app, session, scan, admin):
    inhalt = pdf("Tankstelle 42,00 EUR")
    ablegen(scan, "tank.pdf", inhalt)
    with app.app_context():
        scaneingang.pruefe_ordner()
        from app.services import ablage

        beleg = session.scalars(select(Beleg)).one()
        assert ablage.lies(beleg.sha256) == inhalt
    eintrag = session.scalars(select(Protokoll).where(Protokoll.aktion == "scan_import")).one()
    assert eintrag.details == {"datei": "tank.pdf"}
    assert beleg.hochgeladen_von == admin.id


def test_noch_nicht_fertige_datei_wird_uebersprungen(app, session, scan):
    datei = ablegen(scan, "halb.pdf", pdf(), alter=1)  # Scanner schreibt vielleicht noch
    with app.app_context():
        ergebnis = scaneingang.pruefe_ordner()
    assert ergebnis.leer
    assert datei.exists()
    datei_alt = ablegen(scan, "halb.pdf", pdf(), alter=60)
    with app.app_context():
        assert scaneingang.pruefe_ordner().importiert == ["halb.pdf"]
    assert not datei_alt.exists()


def test_andere_dateitypen_und_versteckte_bleiben_liegen(app, session, scan):
    for name in (
        "notiz.txt",
        "daten.xml",
        "tabelle.csv",
        ".versteckt.pdf",
        "._mac.pdf",
        "x.pdf.tmp",
    ):
        ablegen(scan, name, pdf())
    with app.app_context():
        assert scaneingang.pruefe_ordner().leer
    assert anzahl(session, Beleg) == 0
    assert len(list(scan.iterdir())) == 6


def test_doppelter_scan_kommt_in_den_doppelt_ordner(app, session, scan):
    inhalt = pdf("gleich")
    ablegen(scan, "eins.pdf", inhalt)
    with app.app_context():
        scaneingang.pruefe_ordner()
        ablegen(scan, "zwei.pdf", inhalt)
        ergebnis = scaneingang.pruefe_ordner()
    assert ergebnis.doppelt == ["zwei.pdf"] and not ergebnis.importiert
    assert anzahl(session, Beleg) == 1
    assert (scan / "doppelt" / "zwei.pdf").exists()
    assert session.scalars(select(Protokoll).where(Protokoll.aktion == "scan_doppelt")).one()


def test_kaputte_dateien_kommen_in_den_fehler_ordner(app, session, scan):
    ablegen(scan, "leer.pdf", b"")
    ablegen(scan, "kein.jpg", b"das ist kein Bild")
    ablegen(scan, "gut.pdf", pdf("ok"))
    with app.app_context():
        ergebnis = scaneingang.pruefe_ordner()
    assert ergebnis.importiert == ["gut.pdf"]
    assert {n for n, _ in ergebnis.fehler} == {"leer.pdf", "kein.jpg"}
    assert (scan / "fehler" / "leer.pdf").exists() and (scan / "fehler" / "kein.jpg").exists()
    assert anzahl(session, Beleg) == 1
    assert (
        len(session.scalars(select(Protokoll).where(Protokoll.aktion == "scan_fehler")).all()) == 2
    )
    assert "nicht lesbar" in ergebnis.text()


def test_zu_grosse_datei_wird_abgelehnt(app, session, scan, monkeypatch):
    monkeypatch.setattr("app.services.belege.MAX_GROESSE", 100)
    ablegen(scan, "gross.pdf", pdf("x" * 500))
    with app.app_context():
        ergebnis = scaneingang.pruefe_ordner()
    assert ergebnis.fehler and "20 MB" in ergebnis.fehler[0][1]
    assert (scan / "fehler" / "gross.pdf").exists()


def test_unterordner_eine_ebene_tief_wird_gelesen(app, session, scan):
    ablegen(scan, "brother/2026/scan1.pdf", pdf("tief"))  # zwei Ebenen: ignorieren
    ablegen(scan, "brother/scan2.pdf", pdf("flach"))
    with app.app_context():
        ergebnis = scaneingang.pruefe_ordner()
    assert ergebnis.importiert == ["scan2.pdf"]
    assert (scan / "brother" / "2026" / "scan1.pdf").exists()


def test_symlinks_werden_ignoriert(app, session, scan, tmp_path):
    fremd = tmp_path / "fremd.pdf"
    fremd.write_bytes(pdf("geheim"))
    os.utime(fremd, (time.time() - 60,) * 2)
    scan.mkdir(parents=True, exist_ok=True)
    (scan / "link.pdf").symlink_to(fremd)
    (scan / "ordnerlink").symlink_to(tmp_path)
    with app.app_context():
        assert scaneingang.pruefe_ordner().leer
    assert anzahl(session, Beleg) == 0 and fremd.exists()


def test_gleicher_dateiname_ueberschreibt_nichts(app, session, scan):
    ablegen(scan, "scan.pdf", pdf("erste"))
    with app.app_context():
        scaneingang.pruefe_ordner()
        ablegen(scan, "scan.pdf", pdf("zweite"))
        scaneingang.pruefe_ordner()
    namen = sorted(p.name for p in (scan / "verarbeitet").rglob("*.pdf"))
    assert namen == ["scan-1.pdf", "scan.pdf"]
    assert anzahl(session, Beleg) == 2


def test_fehlender_ordner_ist_kein_fehler(app, session, admin, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "gibt-es-nicht")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "freigabe")
    with app.app_context():
        scaneingang.setze_aktiv(True, admin.id)
        (tmp_path / "gibt-es-nicht").rmdir()
        assert scaneingang.pruefe_ordner().leer


def test_letzter_lauf_und_status(app, session, scan):
    ablegen(scan, "a.pdf", pdf("a"))
    ablegen(scan, "neu.pdf", pdf("b"), alter=1)
    with app.app_context():
        assert scaneingang.status()["letzter_lauf"] is None
        scaneingang.pruefe_ordner()
        stand = scaneingang.status()
    assert stand["letzter_lauf"] is not None
    assert stand["wartend"] == 1 and stand["vorhanden"] and stand["beschreibbar"]
    assert [p.aktion for p in stand["letzte"]] == ["scan_import"]


# ---------- Einstellungsseite ----------


def test_seite_braucht_das_recht_einstellungen(app, client, session, admin):
    neuer_nutzer(session, "mitarbeit@x.example", Rolle.MITARBEITER)
    client.post("/anmelden", data={"email": "mitarbeit@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/einstellungen/scanner").status_code == 403
    assert client.post("/einstellungen/scanner", data={"aktiv": "y"}).status_code == 403
    assert client.post("/einstellungen/scanner/pruefen").status_code == 403


def test_seite_nur_fuer_angemeldete(client, session, admin):
    assert client.get("/einstellungen/scanner").status_code == 302


def test_seite_ein_und_ausschalten(app, angemeldet, session, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "seite-scan")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "freigabe")
    antwort = angemeldet.get("/einstellungen/scanner")
    assert antwort.status_code == 200
    assert "ausgeschaltet" in antwort.get_data(as_text=True)
    angemeldet.post("/einstellungen/scanner", data={"aktiv": "y"})
    html = angemeldet.get("/einstellungen/scanner").get_data(as_text=True)
    assert "eingeschaltet" in html and "Jetzt prüfen" in html and "seite-scan" in html
    angemeldet.post("/einstellungen/scanner", data={})
    assert "ausgeschaltet" in angemeldet.get("/einstellungen/scanner").get_data(as_text=True)


def test_jetzt_pruefen_uebernimmt_scans(app, angemeldet, session, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "knopf")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "freigabe")
    app.config["TEXTERKENNUNG"] = False
    try:
        angemeldet.post("/einstellungen/scanner", data={"aktiv": "y"})
        ablegen(tmp_path / "knopf", "beleg.pdf", pdf("Knopf"), alter=30)
        antwort = angemeldet.post("/einstellungen/scanner/pruefen", follow_redirects=True)
        html = antwort.get_data(as_text=True)
        assert "1 Beleg(e) übernommen" in html
        assert "beleg.pdf" in html
        assert anzahl(session, Beleg) == 1
        assert "Zu prüfen" in angemeldet.get("/").get_data(as_text=True)
    finally:
        app.config["TEXTERKENNUNG"] = True


def test_jetzt_pruefen_ohne_einschalten(angemeldet, session):
    html = angemeldet.post("/einstellungen/scanner/pruefen", follow_redirects=True).get_data(
        as_text=True
    )
    assert "zuerst den Scan-Eingang einschalten" in html


def test_reiter_scanner_ist_sichtbar(angemeldet, session):
    assert "Scanner" in angemeldet.get("/einstellungen/firma").get_data(as_text=True)


def test_zweiter_lauf_gleichzeitig_wird_uebersprungen(app, session, scan):
    from sqlalchemy import text

    from app.extensions import db

    ablegen(scan, "a.pdf", pdf("sperre"))
    with app.app_context():
        fremd = db.engine.connect()
        fremd.execute(text("SELECT pg_advisory_lock(:k)"), {"k": scaneingang.SPERRE_SCHLUESSEL})
        try:
            assert scaneingang.pruefe_ordner().leer
            assert (scan / "a.pdf").exists()
        finally:
            fremd.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": scaneingang.SPERRE_SCHLUESSEL}
            )
            fremd.close()
        assert scaneingang.pruefe_ordner().importiert == ["a.pdf"]


def test_befehl_scan_abruf(app, session, scan):
    ablegen(scan, "cli.pdf", pdf("cli"))
    ergebnis = app.test_cli_runner().invoke(args=["scan-abruf"])
    assert "1 Beleg(e) übernommen" in ergebnis.output


def test_dienst_laeuft_weiter_nach_einem_fehler(app, session, scan, monkeypatch):
    aufrufe = []

    def kaputt():
        aufrufe.append(1)
        raise RuntimeError("Platte weg")

    def schlafen(sekunden):
        if len(aufrufe) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(scaneingang, "pruefe_ordner", kaputt)
    monkeypatch.setattr(scaneingang.time, "sleep", schlafen)
    with app.app_context(), pytest.raises(KeyboardInterrupt):
        scaneingang.dienst(intervall=0)
    assert len(aufrufe) == 2  # der Fehler im ersten Lauf hat den Dienst nicht beendet


# ---------- Netzwerkfreigabe (Samba-Container) ----------


def steuerdatei(tmp_path) -> dict:
    zeilen = (tmp_path / "freigabe" / "status").read_text().splitlines()
    return dict(z.split("=", 1) for z in zeilen)


def test_einschalten_erzeugt_passwort_und_steuerdatei(app, session, scan, tmp_path):
    with app.app_context():
        passwort = scaneingang.passwort()
    assert passwort and len(passwort) == 12 and passwort.isalnum() and passwort.islower()
    assert steuerdatei(tmp_path) == {"aktiv": "1", "kompatibel": "0", "passwort": passwort}
    assert oct((tmp_path / "freigabe" / "status").stat().st_mode & 0o777) == "0o600"


def test_passwort_liegt_verschluesselt_in_der_datenbank(app, session, scan):
    from app.services.einrichtung import aktuelles_gewerbe

    with app.app_context():
        gespeichert = aktuelles_gewerbe().scan_passwort
        assert gespeichert and scaneingang.passwort() not in gespeichert


def test_ausschalten_schaltet_die_freigabe_ab_und_behaelt_das_passwort(
    app, session, scan, admin, tmp_path
):
    with app.app_context():
        passwort = scaneingang.passwort()
        scaneingang.setze_aktiv(False, admin.id)
        assert scaneingang.passwort() == passwort
    assert steuerdatei(tmp_path)["aktiv"] == "0"
    with app.app_context():
        scaneingang.setze_aktiv(True, admin.id)
    assert steuerdatei(tmp_path)["aktiv"] == "1"
    assert steuerdatei(tmp_path)["passwort"] == passwort


def test_freigabe_einzeln_abschaltbar_import_bleibt(app, session, scan, admin, tmp_path):
    with app.app_context():
        scaneingang.setze_aktiv(True, admin.id, freigabe=False)
        assert scaneingang.ist_aktiv() and not scaneingang.freigabe_an()
    assert steuerdatei(tmp_path)["aktiv"] == "0"
    ablegen(scan, "bleibt-import.pdf", pdf("ohne Freigabe"))
    with app.app_context():
        assert scaneingang.pruefe_ordner().importiert == ["bleibt-import.pdf"]


def test_kompatibilitaet_fuer_alte_scanner(app, session, scan, admin, tmp_path):
    with app.app_context():
        scaneingang.setze_aktiv(True, admin.id, kompatibel=True)
    assert steuerdatei(tmp_path)["kompatibel"] == "1"


def test_neues_passwort_ersetzt_das_alte(app, session, scan, admin, tmp_path):
    with app.app_context():
        alt = scaneingang.passwort()
        scaneingang.erneuere_passwort(admin.id)
        neu = scaneingang.passwort()
    assert neu != alt
    assert steuerdatei(tmp_path)["passwort"] == neu
    eintrag = session.scalars(
        select(Protokoll).where(Protokoll.aktion == "scan_passwort_erneuert")
    ).one()
    assert alt not in str(eintrag.details) and neu not in str(eintrag.details)


def test_steuerdatei_nicht_beschreibbar_bricht_nichts_ab(app, session, scan, admin, tmp_path):
    app.config["FREIGABE_VERZEICHNIS"] = "/proc/gibt-es-nicht/freigabe"
    with app.app_context():
        assert scaneingang.schreibe_freigabe() is False
        scaneingang.setze_aktiv(True, admin.id)  # läuft trotzdem durch


def test_dienst_haelt_die_steuerdatei_aktuell(app, session, scan, tmp_path, monkeypatch):
    (tmp_path / "freigabe" / "status").unlink()
    monkeypatch.setattr(
        scaneingang.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    with app.app_context(), pytest.raises(KeyboardInterrupt):
        scaneingang.dienst(intervall=0)
    assert steuerdatei(tmp_path)["aktiv"] == "1"


def test_freigabe_laeuft_prueft_den_port(app, session, scan, monkeypatch):
    class Verbindung:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with app.app_context():
        monkeypatch.setattr(scaneingang.socket, "create_connection", lambda *a, **k: Verbindung())
        assert scaneingang.freigabe_laeuft()

        def kaputt(*a, **k):
            raise OSError("keiner da")

        monkeypatch.setattr(scaneingang.socket, "create_connection", kaputt)
        assert not scaneingang.freigabe_laeuft()
        assert scaneingang.status()["freigabe_laeuft"] is False


def test_aufraeumen_loescht_nur_alte_arbeitskopien(app, session, scan):
    alt = ablegen(scan, "verarbeitet/2026-01/alt.pdf", pdf("alt"), alter=40 * 86400)
    neu = ablegen(scan, "verarbeitet/2026-10/neu.pdf", pdf("neu"), alter=5 * 86400)
    doppelt = ablegen(scan, "doppelt/alt2.pdf", pdf("doppelt"), alter=40 * 86400)
    fehler = ablegen(scan, "fehler/alt3.pdf", pdf("fehler"), alter=40 * 86400)
    eingang = ablegen(scan, "wartet.pdf", pdf("wartet"), alter=40 * 86400)
    with app.app_context():
        assert scaneingang.raeume_auf() == 2
    assert not alt.exists() and not doppelt.exists()
    assert neu.exists() and fehler.exists() and eingang.exists()


# ---------- Seite: Angaben für den Scanner ----------


def test_seite_zeigt_angaben_fuer_den_scanner(app, angemeldet, session, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "s")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "f")
    angemeldet.post("/einstellungen/scanner", data={"aktiv": "y", "freigabe": "y"})
    kopf = {"Host": "192.168.178.40:8000"}
    angemeldet.post(
        "/anmelden", data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT}, headers=kopf
    )
    html = angemeldet.get("/einstellungen/scanner", headers=kopf).get_data(as_text=True)
    assert "192.168.178.40" in html and "scanner</code>" in html
    passwort = (tmp_path / "f" / "status").read_text().split("passwort=")[1].strip()
    assert passwort in html


def test_seite_ohne_freigabe_zeigt_keine_zugangsdaten(app, angemeldet, session, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "s")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "f")
    angemeldet.post("/einstellungen/scanner", data={"aktiv": "y"})  # Freigabe-Haken fehlt
    html = angemeldet.get("/einstellungen/scanner").get_data(as_text=True)
    assert "Diese Angaben trägst du im Scanner ein" not in html
    assert (tmp_path / "f" / "status").read_text().startswith("aktiv=0")


def test_passwort_erneuern_ueber_die_seite(app, angemeldet, session, tmp_path):
    app.config["SCAN_VERZEICHNIS"] = str(tmp_path / "s")
    app.config["FREIGABE_VERZEICHNIS"] = str(tmp_path / "f")
    angemeldet.post("/einstellungen/scanner", data={"aktiv": "y", "freigabe": "y"})
    alt = (tmp_path / "f" / "status").read_text()
    antwort = angemeldet.post("/einstellungen/scanner/passwort", follow_redirects=True)
    assert "Neues Passwort erzeugt" in antwort.get_data(as_text=True)
    assert (tmp_path / "f" / "status").read_text() != alt


def test_passwort_erneuern_braucht_recht_und_einschalten(app, client, session, admin, angemeldet):
    html = angemeldet.post("/einstellungen/scanner/passwort", follow_redirects=True).get_data(
        as_text=True
    )
    assert "zuerst den Scan-Eingang einschalten" in html


# ---------- Samba-Container: Skript im Trockenlauf ----------


def trockenlauf(tmp_path, inhalt):
    import subprocess
    from pathlib import Path

    status = tmp_path / "status"
    if inhalt is not None:
        status.write_text(inhalt)
    protokoll = tmp_path / "protokoll.conf"
    skript = Path(__file__).parent.parent / "docker" / "samba" / "entrypoint.sh"
    ergebnis = subprocess.run(
        ["sh", str(skript)],
        capture_output=True,
        text=True,
        env={
            "TROCKEN": "1",
            "STATUS_DATEI": str(status),
            "PROTOKOLL_DATEI": str(protokoll),
            "PATH": os.environ["PATH"],
        },
        timeout=20,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    return ergebnis.stdout.strip(), protokoll.read_text()


def test_samba_skript_startet_bei_aktiv_und_passwort(tmp_path):
    ausgabe, konfig = trockenlauf(tmp_path, "aktiv=1\nkompatibel=0\npasswort=abc123xyz789\n")
    assert ausgabe == "START protokoll=SMB2"
    assert konfig == "server min protocol = SMB2\n"


def test_samba_skript_kompatibel_erlaubt_smb1(tmp_path):
    ausgabe, konfig = trockenlauf(tmp_path, "aktiv=1\nkompatibel=1\npasswort=abc123xyz789\n")
    assert ausgabe == "START protokoll=NT1"
    assert "server min protocol = NT1" in konfig


@pytest.mark.parametrize(
    "inhalt",
    [
        None,  # keine Datei
        "aktiv=0\nkompatibel=0\npasswort=abc123xyz789\n",  # ausgeschaltet
        "aktiv=1\nkompatibel=0\npasswort=\n",  # kein Passwort
        "aktiv=1\nkompatibel=0\npasswort=Gross;rm -rf\n",  # unzulässige Zeichen
    ],
)
def test_samba_skript_bleibt_sonst_aus(tmp_path, inhalt):
    ausgabe, _ = trockenlauf(tmp_path, inhalt)
    assert ausgabe == "STOP"
