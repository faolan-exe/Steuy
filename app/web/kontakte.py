from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.rollen import Recht
from app.extensions import db
from app.models import Kontakt, Rechnung
from app.services.kontakte import (
    aendere_kontakt,
    gleichnamige_kontakte,
    lege_kontakt_an,
    setze_archiviert,
    suche_kontakte,
    typ_von,
    uebersicht,
)
from app.web.formulare import KontaktFormular
from app.web.rechte import braucht_recht

bp = Blueprint("kontakte", __name__, url_prefix="/kontakte")

FILTER = {"alle": "Alle", "kunden": "Kunden", "lieferanten": "Lieferanten"}


def _kontakt(kontakt_id: int) -> Kontakt:
    return db.session.get(Kontakt, kontakt_id) or abort(404)


@bp.get("")
@braucht_recht(Recht.ANSEHEN)
def liste():
    filter = request.args.get("filter", "alle")
    filter = filter if filter in FILTER else "alle"
    suche = request.args.get("q", "")
    archiv = request.args.get("archiv") == "1"
    kontakte = suche_kontakte(suche, filter, archiv)
    vorlage = "kontakte_zeilen.html" if request.headers.get("HX-Request") else "kontakte.html"
    return render_template(
        vorlage, kontakte=kontakte, filter=filter, filter_namen=FILTER, suche=suche, archiv=archiv
    )


def _entwurf_ohne_kontakt(rechnung_id: str | None) -> Rechnung | None:
    """Rechnungsentwurf, dessen eingetippter Kunde als Kontakt gespeichert werden soll."""
    if not (rechnung_id or "").isdigit():
        return None
    rechnung = db.session.get(Rechnung, int(rechnung_id))
    if rechnung is None or not rechnung.ist_entwurf or rechnung.kontakt_id is not None:
        return None
    return rechnung


def _aus_rechnung(rechnung: Rechnung) -> dict:
    name = (rechnung.empfaenger_name or "").strip()
    woerter = name.split()
    return {
        "art": "firma",
        "firmenname": name,
        "vorname": " ".join(woerter[:-1]),
        "nachname": woerter[-1] if woerter else "",
        "typ": "kunde",
        "adresszusatz": rechnung.empfaenger_zusatz,
        "strasse": rechnung.empfaenger_strasse,
        "plz": rechnung.empfaenger_plz,
        "ort": rechnung.empfaenger_ort,
        "land": rechnung.empfaenger_land or "Deutschland",
    }


@bp.route("/neu", methods=["GET", "POST"])
@braucht_recht(Recht.STAMMDATEN)
def neu():
    fuer = _entwurf_ohne_kontakt(request.values.get("fuer"))
    vorbelegt = _aus_rechnung(fuer) if fuer and request.method == "GET" else None
    formular = KontaktFormular(data=vorbelegt) if vorbelegt else KontaktFormular()
    doppelte = []
    if formular.validate_on_submit():
        if formular.art.data == "firma":
            name = formular.firmenname.data
        else:
            name = f"{formular.vorname.data or ''} {formular.nachname.data or ''}"
        doppelte = gleichnamige_kontakte(name)
        if not doppelte or request.form.get("doppelt_ok"):
            kontakt = lege_kontakt_an(formular.data, current_user.id)
            if fuer is not None:
                fuer.kontakt_id = kontakt.id
                db.session.commit()
                flash(f"{kontakt.name} wurde angelegt und mit dem Entwurf verbunden.")
                return redirect(url_for("rechnungen.bearbeiten", rechnung_id=fuer.id))
            flash(f"{kontakt.name} wurde angelegt.")
            return redirect(url_for("kontakte.detail", kontakt_id=kontakt.id))
    return render_template(
        "kontakt_formular.html", formular=formular, kontakt=None, doppelte=doppelte, fuer=fuer
    )


@bp.get("/<int:kontakt_id>")
@braucht_recht(Recht.ANSEHEN)
def detail(kontakt_id: int):
    kontakt = _kontakt(kontakt_id)
    return render_template(
        "kontakt.html", kontakt=kontakt, typ=typ_von(kontakt), u=uebersicht(kontakt)
    )


@bp.route("/<int:kontakt_id>/bearbeiten", methods=["GET", "POST"])
@braucht_recht(Recht.STAMMDATEN)
def bearbeiten(kontakt_id: int):
    kontakt = _kontakt(kontakt_id)
    formular = KontaktFormular(obj=kontakt, typ=typ_von(kontakt))
    if formular.validate_on_submit():
        aenderungen = aendere_kontakt(kontakt, formular.data, current_user.id)
        flash("Gespeichert." if aenderungen else "Keine Änderungen.")
        return redirect(url_for("kontakte.detail", kontakt_id=kontakt.id))
    return render_template("kontakt_formular.html", formular=formular, kontakt=kontakt)


@bp.post("/<int:kontakt_id>/archivieren")
@braucht_recht(Recht.STAMMDATEN)
def archivieren(kontakt_id: int):
    kontakt = _kontakt(kontakt_id)
    setze_archiviert(kontakt, not kontakt.archiviert, current_user.id)
    flash(f"{kontakt.name} wurde {'archiviert' if kontakt.archiviert else 'wiederhergestellt'}.")
    return redirect(url_for("kontakte.detail", kontakt_id=kontakt.id))
