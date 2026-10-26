import time

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user

from app.extensions import db
from app.models import Nutzer
from app.services import passkey
from app.services.anmeldung import (
    ZuVieleVersuche,
    protokolliere_abmeldung,
    pruefe_anmeldung,
    pruefe_zweiten_faktor,
)
from app.services.zwei_faktor import ZweiFaktorFehler, sende_mail_code
from app.web.formulare import AnmeldeFormular, CodeFormular

bp = Blueprint("auth", __name__)


def sicheres_ziel(ziel: str | None) -> str:
    """Nur relative Pfade dieser App, keine Weiterleitung auf fremde Seiten."""
    if ziel and ziel.startswith("/") and not ziel.startswith("//") and "\\" not in ziel:
        return ziel
    return url_for("allgemein.start")


@bp.route("/anmelden", methods=["GET", "POST"])
def anmelden():
    if current_user.is_authenticated:
        return redirect(url_for("allgemein.start"))

    formular = AnmeldeFormular()
    fehler = None
    if formular.validate_on_submit():
        try:
            nutzer = pruefe_anmeldung(
                formular.email.data, formular.passwort.data, request.remote_addr or "unbekannt"
            )
        except ZuVieleVersuche as sperre:
            return render_template("anmelden.html", formular=formular, fehler=str(sperre)), 429
        if nutzer and nutzer.totp_aktiv:
            session.clear()
            session["zweiter_faktor"] = {
                "id": nutzer.id,
                "bis": time.time() + 300,
                "ziel": sicheres_ziel(request.args.get("next")),
            }
            if nutzer.zwei_faktor_art == "mail":
                _mail_code_senden(nutzer)
            return redirect(url_for("auth.zweiter_faktor"))
        if nutzer:
            session.clear()
            login_user(nutzer)
            return redirect(sicheres_ziel(request.args.get("next")))
        fehler = "E-Mail oder Passwort ist falsch."

    return render_template("anmelden.html", formular=formular, fehler=fehler)


def _mail_code_senden(nutzer: Nutzer) -> None:
    try:
        sende_mail_code(nutzer)
    except ZweiFaktorFehler as fehler:
        flash(str(fehler))
    else:
        flash(f"Code an {nutzer.email} geschickt.")


def _offener_nutzer() -> tuple[dict | None, Nutzer | None]:
    offen = session.get("zweiter_faktor")
    if not offen or offen.get("bis", 0) < time.time():
        session.pop("zweiter_faktor", None)
        return None, None
    nutzer = db.session.get(Nutzer, offen["id"])
    if not nutzer or not nutzer.is_active:
        session.clear()
        return None, None
    return offen, nutzer


@bp.post("/anmelden/code/neu")
def code_neu_senden():
    offen, nutzer = _offener_nutzer()
    if not nutzer:
        return redirect(url_for("auth.anmelden"))
    if nutzer.zwei_faktor_art == "mail":
        _mail_code_senden(nutzer)
    return redirect(url_for("auth.zweiter_faktor"))


@bp.route("/anmelden/code", methods=["GET", "POST"])
def zweiter_faktor():
    offen, nutzer = _offener_nutzer()
    if not nutzer:
        return redirect(url_for("auth.anmelden"))

    formular = CodeFormular()
    fehler = None
    if formular.validate_on_submit():
        try:
            gueltig = pruefe_zweiten_faktor(
                nutzer, formular.code.data, request.remote_addr or "unbekannt"
            )
        except ZuVieleVersuche as sperre:
            return render_template(
                "zweiter_faktor.html", formular=formular, fehler=str(sperre), nutzer=nutzer
            ), 429
        if gueltig:
            ziel = offen.get("ziel") or url_for("allgemein.start")
            session.clear()
            login_user(nutzer)
            return redirect(ziel)
        fehler = "Der Code stimmt nicht."
    return render_template("zweiter_faktor.html", formular=formular, fehler=fehler, nutzer=nutzer)


@bp.post("/anmelden/passkey/optionen")
def passkey_optionen():
    if current_user.is_authenticated:
        return jsonify(fehler="Du bist schon angemeldet."), 400
    try:
        optionen = passkey.anmeldung_optionen()
    except passkey.PasskeyFehler as fehler:
        return jsonify(fehler=str(fehler)), 400
    return Response(optionen, mimetype="application/json")


@bp.post("/anmelden/passkey")
def passkey_anmelden():
    daten = request.get_json(silent=True) or {}
    try:
        nutzer = passkey.anmeldung_pruefen(daten.get("credential"))
    except passkey.PasskeyFehler as fehler:
        return jsonify(fehler=str(fehler)), 400
    session.clear()
    login_user(nutzer)
    session["passkey_anmeldung"] = True
    return jsonify(ok=True, ziel=sicheres_ziel(daten.get("ziel")))


@bp.post("/abmelden")
def abmelden():
    if current_user.is_authenticated:
        protokolliere_abmeldung(current_user.id)
    logout_user()
    session.clear()
    return redirect(url_for("auth.anmelden"))
