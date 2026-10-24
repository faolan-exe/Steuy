from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.rollen import Recht
from app.extensions import db
from app.models import Kontakt
from app.services.kontakte import (
    aendere_kontakt,
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


@bp.route("/neu", methods=["GET", "POST"])
@braucht_recht(Recht.STAMMDATEN)
def neu():
    formular = KontaktFormular()
    if formular.validate_on_submit():
        kontakt = lege_kontakt_an(formular.data, current_user.id)
        flash(f"{kontakt.name} wurde angelegt.")
        return redirect(url_for("kontakte.detail", kontakt_id=kontakt.id))
    return render_template("kontakt_formular.html", formular=formular, kontakt=None)


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
