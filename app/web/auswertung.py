import csv
import io
from datetime import date

from flask import Blueprint, Response, render_template, request, send_file
from flask_login import current_user

from app.domain.geld import cent_zu_euro
from app.domain.rollen import Recht
from app.services.auswertung_pdf import euer_pdf as erzeuge_euer_pdf
from app.services.euer import berechne, jahre_mit_daten
from app.services.export import gesamt_zip, steuerberater_zip, wechsel_zip
from app.web.formulare import WechselExportFormular
from app.web.rechte import braucht_recht

bp = Blueprint("auswertung", __name__, url_prefix="/auswertung")


def _jahr() -> int:
    wert = request.args.get("jahr", "")
    return int(wert) if wert.isdigit() and 2000 <= int(wert) <= 2100 else date.today().year


def _betrag(cent: int) -> str:
    """Für CSV: deutsches Format ohne Tausenderpunkt und ohne €, z. B. 1234,56."""
    return cent_zu_euro(cent)[:-2].replace(".", "")


@bp.get("")
@braucht_recht(Recht.AUSWERTUNGEN)
def euer():
    jahr = _jahr()
    jahre = sorted(set(jahre_mit_daten()) | {date.today().year, jahr})
    return render_template("auswertung.html", e=berechne(jahr), jahre=jahre)


@bp.get("/euer.csv")
@braucht_recht(Recht.AUSWERTUNGEN)
def euer_csv():
    e = berechne(_jahr())
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(["Anlage EÜR", e.jahr, f"Zeilen laut Vordruck {e.vordruck_jahr}"])
    schreiber.writerow(["Zeile", "Kennzahl", "Bezeichnung", "Betrag EUR"])
    for zeile, betrag, _ in e.einnahmen + e.ausgaben:
        nummer = zeile.nummer if zeile.nummer > 0 else ""
        schreiber.writerow([nummer, zeile.kennzahl or "", zeile.bezeichnung, _betrag(betrag)])
    schreiber.writerow(["", "", "Summe Betriebseinnahmen", _betrag(e.summe_einnahmen)])
    schreiber.writerow(["", "", "Summe Betriebsausgaben", _betrag(e.summe_ausgaben)])
    schreiber.writerow(["", "", "Gewinn/Verlust", _betrag(e.gewinn)])
    schreiber.writerow([])
    schreiber.writerow(["Datum", "Zeile", "Posten", "Betrag EUR"])
    for zeile, _, posten in e.einnahmen + e.ausgaben:
        for p in posten:
            nummer = zeile.nummer if zeile.nummer > 0 else ""
            schreiber.writerow(
                [p.datum.strftime("%d.%m.%Y"), nummer, p.text, _betrag(p.betrag_cent)]
            )
    return Response(
        "﻿" + puffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="EUER-{e.jahr}.csv"'},
    )


@bp.get("/euer.pdf")
@braucht_recht(Recht.AUSWERTUNGEN)
def euer_pdf():
    e = berechne(_jahr())
    return Response(
        erzeuge_euer_pdf(e),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="EUER-{e.jahr}.pdf"'},
    )


@bp.get("/export.zip")
@braucht_recht(Recht.EXPORT)
def export_zip():
    jahr = _jahr()
    return send_file(
        steuerberater_zip(jahr, current_user.id),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"steuy-Export-{jahr}.zip",
    )


@bp.get("/gesamtexport.zip")
@braucht_recht(Recht.EINSTELLUNGEN)
def gesamtexport_zip():
    return send_file(
        gesamt_zip(current_user.id),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"steuy-Gesamtexport-{date.today():%Y-%m-%d}.zip",
    )


@bp.route("/wechsel", methods=["GET", "POST"])
@braucht_recht(Recht.EXPORT)
def wechsel():
    formular = WechselExportFormular()
    if formular.validate_on_submit():
        return send_file(
            wechsel_zip(
                formular.kontenrahmen.data,
                formular.beraternummer.data,
                formular.mandantennummer.data,
                current_user.id,
            ),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"steuy-Wechsel-{date.today():%Y-%m-%d}.zip",
        )
    return render_template("wechsel.html", formular=formular)
