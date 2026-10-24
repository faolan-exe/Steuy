from datetime import date

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import login_user

from app.services.einrichtung import grenze, ist_eingerichtet, richte_ein
from app.web.formulare import EinrichtungFormular

bp = Blueprint("einrichtung", __name__)


@bp.route("/einrichtung", methods=["GET", "POST"])
def einrichten():
    if ist_eingerichtet():
        abort(404)

    formular = EinrichtungFormular()
    if formular.validate_on_submit():
        admin = richte_ein(
            formular.data,
            formular.admin_name.data,
            formular.admin_email.data,
            formular.passwort.data,
            erfahrung=formular.erfahrung.data,
            kennt_steuy=formular.kennt_steuy.data == "ja",
        )
        login_user(admin)
        return redirect(url_for("rundgang.entscheidung"))

    return render_template("einrichtung.html", formular=formular, grenze=grenze(date.today().year))
