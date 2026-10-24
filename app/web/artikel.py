from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.geld import cent_zu_euro
from app.domain.rollen import Recht
from app.extensions import db
from app.models import Artikel
from app.services.artikel import (
    ArtikelnummerVergeben,
    aendere_artikel,
    lege_artikel_an,
    setze_archiviert,
    suche_artikel,
)
from app.web.formulare import ArtikelFormular
from app.web.rechte import braucht_recht

bp = Blueprint("artikel", __name__, url_prefix="/artikel")

FILTER = {"alle": "Alle", "produkte": "Produkte", "services": "Services"}


def _artikel(artikel_id: int) -> Artikel:
    return db.session.get(Artikel, artikel_id) or abort(404)


def _daten(formular: ArtikelFormular) -> dict:
    return {**formular.data, "preis_cent": formular.preis_cent}


@bp.get("")
@braucht_recht(Recht.ANSEHEN)
def liste():
    filter = request.args.get("filter", "alle")
    filter = filter if filter in FILTER else "alle"
    suche = request.args.get("q", "")
    archiv = request.args.get("archiv") == "1"
    artikel = suche_artikel(suche, filter, archiv)
    vorlage = "artikel_zeilen.html" if request.headers.get("HX-Request") else "artikel.html"
    return render_template(
        vorlage,
        artikelliste=artikel,
        filter=filter,
        filter_namen=FILTER,
        suche=suche,
        archiv=archiv,
    )


@bp.route("/neu", methods=["GET", "POST"])
@braucht_recht(Recht.STAMMDATEN)
def neu():
    formular = ArtikelFormular()
    if formular.validate_on_submit():
        try:
            artikel = lege_artikel_an(_daten(formular), current_user.id)
        except ArtikelnummerVergeben as fehler:
            formular.artikelnummer.errors.append(str(fehler))
        else:
            flash(f"{artikel.bezeichnung} wurde angelegt.")
            return redirect(url_for("artikel.liste"))
    return render_template("artikel_formular.html", formular=formular, artikel=None)


@bp.route("/<int:artikel_id>/bearbeiten", methods=["GET", "POST"])
@braucht_recht(Recht.STAMMDATEN)
def bearbeiten(artikel_id: int):
    artikel = _artikel(artikel_id)
    formular = ArtikelFormular(obj=artikel, preis=cent_zu_euro(artikel.preis_cent)[:-2])
    if formular.validate_on_submit():
        try:
            aenderungen = aendere_artikel(artikel, _daten(formular), current_user.id)
        except ArtikelnummerVergeben as fehler:
            formular.artikelnummer.errors.append(str(fehler))
        else:
            flash("Gespeichert." if aenderungen else "Keine Änderungen.")
            return redirect(url_for("artikel.liste"))
    return render_template("artikel_formular.html", formular=formular, artikel=artikel)


@bp.post("/<int:artikel_id>/archivieren")
@braucht_recht(Recht.STAMMDATEN)
def archivieren(artikel_id: int):
    artikel = _artikel(artikel_id)
    setze_archiviert(artikel, not artikel.archiviert, current_user.id)
    zustand = "archiviert" if artikel.archiviert else "wiederhergestellt"
    flash(f"{artikel.bezeichnung} wurde {zustand}.")
    return redirect(url_for("artikel.liste"))
