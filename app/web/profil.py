import io

import segno
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.rollen import Recht
from app.extensions import db
from app.services.mail import eingerichtet as mail_eingerichtet
from app.services.protokoll import protokolliere
from app.services.zwei_faktor import (
    ZweiFaktorFehler,
    aendere_passwort,
    bestaetige_einrichtung,
    bestaetige_mail_einrichtung,
    deaktiviere,
    einrichtungs_uri,
    neue_codes,
    offene_codes,
    offenes_geheimnis,
    starte_einrichtung,
    starte_mail_einrichtung,
)
from app.web.formulare import CodeFormular, PasswortAendernFormular
from app.web.rechte import braucht_recht

bp = Blueprint("profil", __name__, url_prefix="/profil")


def _qr(uri: str) -> str:
    puffer = io.BytesIO()
    segno.make_qr(uri, error="m").save(
        puffer, kind="svg", xmldecl=False, svgns=True, omitsize=True, border=4, light="#fff"
    )
    return puffer.getvalue().decode()


@bp.route("", methods=["GET", "POST"])
@braucht_recht(Recht.ANSEHEN)
def profil():
    formular = PasswortAendernFormular()
    if formular.validate_on_submit():
        try:
            aendere_passwort(current_user, formular.alt.data, formular.neu.data)
        except ZweiFaktorFehler as fehler:
            formular.alt.errors.append(str(fehler))
        else:
            flash("Passwort geändert.")
            return redirect(url_for("profil.profil"))
    return render_template(
        "profil.html", formular=formular, offene_codes=offene_codes(current_user)
    )


@bp.route("/zwei-faktor", methods=["GET", "POST"])
def zwei_faktor():
    # Ohne @braucht_recht: muss auch bei verpflichtender 2FA erreichbar sein (siehe zugang.py)
    if not current_user.is_authenticated:
        return redirect(url_for("auth.anmelden"))
    if current_user.totp_aktiv:
        return redirect(url_for("profil.profil"))

    formular = CodeFormular()
    geheimnis = offenes_geheimnis(current_user)
    if request.method == "GET" or not geheimnis:
        geheimnis, uri = starte_einrichtung(current_user)
    else:
        uri = einrichtungs_uri(geheimnis, current_user.email)
        if formular.validate_on_submit():
            try:
                codes = bestaetige_einrichtung(current_user, formular.code.data)
            except ZweiFaktorFehler as fehler:
                formular.code.errors.append(str(fehler))
            else:
                return render_template("wiederherstellungscodes.html", codes=codes)
    lesbar = " ".join(geheimnis[i : i + 4] for i in range(0, len(geheimnis), 4))
    return render_template(
        "zwei_faktor.html",
        formular=formular,
        qr=_qr(uri),
        geheimnis=lesbar,
        mail_moeglich=mail_eingerichtet(),
    )


@bp.route("/zwei-faktor/mail", methods=["GET", "POST"])
def zwei_faktor_mail():
    # Ohne @braucht_recht wie zwei_faktor: auch bei verpflichtender 2FA erreichbar
    if not current_user.is_authenticated:
        return redirect(url_for("auth.anmelden"))
    if current_user.totp_aktiv:
        return redirect(url_for("profil.profil"))
    formular = CodeFormular()
    if request.method == "GET" or request.form.get("neu"):
        try:
            starte_mail_einrichtung(current_user)
        except ZweiFaktorFehler as fehler:
            flash(str(fehler))
            if not mail_eingerichtet():
                return redirect(url_for("profil.zwei_faktor"))
        else:
            flash(f"Code an {current_user.email} geschickt.")
        if request.method == "POST":
            return redirect(url_for("profil.zwei_faktor_mail"))
    elif formular.validate_on_submit():
        try:
            codes = bestaetige_mail_einrichtung(current_user, formular.code.data)
        except ZweiFaktorFehler as fehler:
            formular.code.errors.append(str(fehler))
        else:
            return render_template("wiederherstellungscodes.html", codes=codes)
    return render_template("zwei_faktor_mail.html", formular=formular)


@bp.post("/zwei-faktor/codes")
@braucht_recht(Recht.ANSEHEN)
def neue_wiederherstellungscodes():
    try:
        codes = neue_codes(current_user, request.form.get("passwort", ""))
    except ZweiFaktorFehler as fehler:
        flash(str(fehler))
        return redirect(url_for("profil.profil"))
    return render_template("wiederherstellungscodes.html", codes=codes)


@bp.post("/zwei-faktor/deaktivieren")
@braucht_recht(Recht.ANSEHEN)
def zwei_faktor_deaktivieren():
    try:
        deaktiviere(current_user, current_user.id, request.form.get("passwort", ""))
    except ZweiFaktorFehler as fehler:
        flash(str(fehler))
    else:
        flash("Zwei-Faktor-Anmeldung ausgeschaltet.")
    return redirect(url_for("profil.profil"))


@bp.post("/hilfe")
@braucht_recht(Recht.ANSEHEN)
def hilfe_umschalten():
    an = request.form.get("hilfe_anzeigen") == "y"
    if current_user.hilfe_anzeigen != an:
        current_user.hilfe_anzeigen = an
        protokolliere(
            "hilfe_umgeschaltet", nutzer_id=current_user.id, details={"hilfe_anzeigen": an}
        )
        db.session.commit()
    flash("Hilfe-Fragezeichen werden angezeigt." if an else "Hilfe-Fragezeichen ausgeblendet.")
    return redirect(url_for("profil.profil") + "#darstellung")


@bp.post("/wochenmail")
@braucht_recht(Recht.ANSEHEN)
def wochenmail_umschalten():
    an = request.form.get("wochenmail") == "y"
    if current_user.wochenmail != an:
        current_user.wochenmail = an
        protokolliere("wochenmail_umgeschaltet", nutzer_id=current_user.id, details={"an": an})
        db.session.commit()
    flash(
        "Wöchentliche Zusammenfassung eingeschaltet."
        if an
        else "Wöchentliche Zusammenfassung abbestellt."
    )
    return redirect(url_for("profil.profil") + "#email")
