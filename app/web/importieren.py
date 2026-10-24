import base64
import binascii
import re
import secrets
import shutil
import time
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.csvimport import FELDER, PFLICHT, CsvUngueltig, lies, vorschlag
from app.domain.rollen import Recht
from app.services.archivimport import (
    importiere_archiv,
    ist_zahlungsliste,
    uebernehme_zahlungen,
    zahlungslisten_im_zip,
)
from app.services.csvimport import importiere_artikel, importiere_kontakte
from app.services.kontakte import TYPEN
from app.web.rechte import braucht_recht

bp = Blueprint("importieren", __name__, url_prefix="/import")


def _art() -> str:
    art = request.values.get("art", "kontakte")
    return art if art in FELDER else "kontakte"


def _typ() -> str:
    typ = request.values.get("typ", "kunde")
    return typ if typ in TYPEN else "kunde"


@bp.get("")
@braucht_recht(Recht.STAMMDATEN)
def start():
    return render_template("import_start.html", art=_art(), typ=_typ())


def _zuordnung_aus_formular(art: str, spalten: int) -> dict[str, int | None]:
    zuordnung = {}
    for feld in FELDER[art]:
        wert = request.form.get(f"feld_{feld}", "")
        zuordnung[feld] = int(wert) if wert.isdigit() and int(wert) < spalten else None
    return zuordnung


def _seite(art, typ, inhalt, kopf, zeilen, zuordnung, ergebnis=None):
    fehlend = [FELDER[art][f][0] for f in PFLICHT[art] if zuordnung.get(f) is None]
    return render_template(
        "import_zuordnen.html",
        art=art,
        typ=typ,
        felder=FELDER[art],
        kopf=kopf,
        beispiele=zeilen[:5],
        anzahl=len(zeilen),
        zuordnung=zuordnung,
        daten=base64.b64encode(inhalt).decode(),
        ergebnis=ergebnis,
        fehlend=fehlend,
    )


@bp.post("/zuordnen")
@braucht_recht(Recht.STAMMDATEN)
def zuordnen():
    art, typ = _art(), _typ()
    datei = request.files.get("datei")
    inhalt = datei.read() if datei else b""
    try:
        kopf, zeilen = lies(inhalt)
    except CsvUngueltig as fehler:
        flash(str(fehler))
        return redirect(url_for("importieren.start", art=art, typ=typ))
    return _seite(art, typ, inhalt, kopf, zeilen, vorschlag(art, kopf))


@bp.post("/ausfuehren")
@braucht_recht(Recht.STAMMDATEN)
def ausfuehren():
    art, typ = _art(), _typ()
    try:
        inhalt = base64.b64decode(request.form.get("daten", ""), validate=True)
        kopf, zeilen = lies(inhalt)
    except (CsvUngueltig, binascii.Error, ValueError):
        flash("Die Datei ging verloren. Bitte noch einmal hochladen.")
        return redirect(url_for("importieren.start", art=art, typ=typ))
    zuordnung = _zuordnung_aus_formular(art, len(kopf))
    pruefen = request.form.get("aktion") != "importieren"
    if any(zuordnung.get(f) is None for f in PFLICHT[art]):
        pruefen = True
    if art == "kontakte":
        ergebnis = importiere_kontakte(zeilen, zuordnung, typ, current_user.id, pruefen=pruefen)
    else:
        ergebnis = importiere_artikel(zeilen, zuordnung, current_user.id, pruefen=pruefen)
    if pruefen:
        return _seite(art, typ, inhalt, kopf, zeilen, zuordnung, ergebnis)
    return render_template("import_ergebnis.html", art=art, ergebnis=ergebnis)


# ---------- Belegarchiv aus Lexware (DATEV-Format) ----------

TOKEN = re.compile(r"^[0-9a-f]{32}$")
ZWISCHENSPEICHER_TAGE = 1


def _zwischenspeicher() -> Path:
    return Path(current_app.config["ABLAGE_VERZEICHNIS"]).parent / "archiv-upload"


def _alte_aufraeumen(ordner: Path) -> None:
    if not ordner.exists():
        return
    grenze = time.time() - ZWISCHENSPEICHER_TAGE * 86400
    for unter in ordner.iterdir():
        if unter.is_dir() and unter.stat().st_mtime < grenze:
            shutil.rmtree(unter, ignore_errors=True)


@bp.get("/archiv")
@braucht_recht(Recht.BUCHEN)
def archiv_start():
    return render_template("import_archiv.html", ergebnisse=None, token=None, fertig=False)


@bp.post("/archiv")
@braucht_recht(Recht.BUCHEN)
def archiv():
    ordner = _zwischenspeicher()
    token = request.form.get("token", "")
    if token and TOKEN.match(token) and (ordner / token).is_dir():
        pfad = ordner / token
    else:
        hochgeladen = [d for d in request.files.getlist("dateien") if d and d.filename]
        if not hochgeladen:
            flash("Bitte mindestens eine ZIP-Datei auswählen.")
            return redirect(url_for("importieren.archiv_start"))
        _alte_aufraeumen(ordner)
        token = secrets.token_hex(16)
        pfad = ordner / token
        pfad.mkdir(parents=True)
        for nr, datei in enumerate(hochgeladen, start=1):
            (pfad / f"{nr:03d}.zip").write_bytes(datei.read())
            (pfad / f"{nr:03d}.name").write_text(datei.filename[:200], encoding="utf-8")
    pruefen = request.form.get("aktion") != "importieren"
    bekannt: set = set()
    archive, listen = [], []
    for zip_datei in sorted(pfad.glob("*.zip")):
        name = zip_datei.with_suffix(".name").read_text(encoding="utf-8")
        roh = zip_datei.read_bytes()
        if ist_zahlungsliste(roh):
            listen.append((name, roh))
        elif enthalten := zahlungslisten_im_zip(roh):
            listen.extend((name, daten) for daten in enthalten)
        else:
            archive.append((name, roh))
    ergebnisse = [
        (name, importiere_archiv(roh, current_user.id, pruefen, bekannt)) for name, roh in archive
    ]
    # Zahlungen erst nach den Buchungen, damit es etwas zum Zuordnen gibt
    ergebnisse += [
        (name, uebernehme_zahlungen(roh, current_user.id, pruefen, bekannt)) for name, roh in listen
    ]
    if not pruefen:
        shutil.rmtree(pfad, ignore_errors=True)
    return render_template(
        "import_archiv.html",
        ergebnisse=ergebnisse,
        token=token if pruefen else None,
        fertig=not pruefen,
    )
