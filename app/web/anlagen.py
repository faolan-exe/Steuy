from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.afa import ARTEN, SOFORT, AfaUngueltig, plan
from app.domain.rollen import Recht
from app.extensions import db
from app.models import Buchung, Nutzungsdauer
from app.services.anlagen import kann_anlagegut_werden, lege_an, verzeichnis
from app.web.formulare import AnlagegutFormular
from app.web.rechte import braucht_recht

bp = Blueprint("anlagen", __name__)


@bp.route("/buchungen/<int:buchung_id>/anlagegut", methods=["GET", "POST"])
@braucht_recht(Recht.BUCHEN)
def anlegen(buchung_id: int):
    buchung = db.session.get(Buchung, buchung_id)
    if not buchung:
        abort(404)
    grund = kann_anlagegut_werden(buchung)
    if grund:
        flash(grund)
        return redirect(url_for("belege.buchung", buchung_id=buchung.id))
    formular = AnlagegutFormular()
    if request.method == "GET":
        formular.bezeichnung.data = buchung.beschreibung or buchung.partner or ""
        formular.anschaffungsdatum.data = buchung.belegdatum
    vorschau = None
    if formular.validate_on_submit():
        dauer = 1 if formular.art.data in SOFORT else formular.nutzungsdauer_jahre.data
        if request.form.get("aktion") == "anlegen":
            try:
                lege_an(
                    buchung,
                    bezeichnung=formular.bezeichnung.data,
                    art=formular.art.data,
                    anschaffungsdatum=formular.anschaffungsdatum.data,
                    nutzungsdauer_jahre=dauer,
                    nutzer_id=current_user.id,
                )
            except AfaUngueltig as fehler:
                formular.nutzungsdauer_jahre.errors = [str(fehler)]
            else:
                flash("Anlagegut angelegt. Die Abschreibung erscheint in der EÜR.")
                return redirect(url_for("belege.buchung", buchung_id=buchung.id))
        else:
            vorschau = plan(
                buchung.betrag_cent, formular.anschaffungsdatum.data, dauer, formular.art.data
            )
    dauern = db.session.execute(
        db.select(Nutzungsdauer).order_by(Nutzungsdauer.bezeichnung)
    ).scalars()
    return render_template(
        "anlagegut.html", b=buchung, formular=formular, vorschau=vorschau, dauern=list(dauern)
    )


@bp.get("/auswertung/anlagen")
@braucht_recht(Recht.AUSWERTUNGEN)
def verzeichnis_seite():
    wert = request.args.get("jahr", "")
    jahr = int(wert) if wert.isdigit() and 2000 <= int(wert) <= 2100 else date.today().year
    zeilen = verzeichnis(jahr)
    summen = {}
    for z in zeilen:
        summen[z.kennzahl] = summen.get(z.kennzahl, 0) + z.afa_cent
    return render_template("anlagen.html", jahr=jahr, zeilen=zeilen, summen=summen, arten=ARTEN)
