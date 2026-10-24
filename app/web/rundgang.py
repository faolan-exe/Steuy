from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.rollen import Recht
from app.domain.rundgang import STUFEN, frage_zum_start
from app.services import rundgang as dienst
from app.web.rechte import braucht_recht

bp = Blueprint("rundgang", __name__, url_prefix="/rundgang")


def _zum_schritt():
    ziel = dienst.aktueller_schritt(current_user)
    if ziel is None:
        return redirect(url_for("allgemein.start"))
    return redirect(url_for(ziel[0].endpunkt))


@bp.get("")
@braucht_recht(Recht.ANSEHEN)
def entscheidung():
    """Nach der Einrichtung: je nach Antworten direkt starten oder nachfragen."""
    frage = frage_zum_start(current_user.erfahrung, current_user.kennt_steuy)
    if frage == "starten" and not current_user.rundgang_fertig:
        dienst.starte(current_user)
        return _zum_schritt()
    if current_user.rundgang_fertig or dienst.aktiv(current_user):
        return redirect(url_for("allgemein.start"))
    return render_template("rundgang_frage.html", frage=frage)


@bp.post("/start")
@braucht_recht(Recht.ANSEHEN)
def start():
    dienst.starte(current_user)
    return _zum_schritt()


@bp.post("/ueberspringen")
@braucht_recht(Recht.ANSEHEN)
def ueberspringen():
    dienst.ueberspringe(current_user)
    flash("Alles klar. Den Rundgang findest du jederzeit im Profil.")
    return redirect(url_for("allgemein.start"))


@bp.post("/weiter")
@braucht_recht(Recht.ANSEHEN)
def weiter():
    if not dienst.weiter(current_user):
        flash("Der Rundgang ist zu Ende. Viel Erfolg!")
        return redirect(url_for("allgemein.start"))
    return _zum_schritt()


@bp.post("/zurueck")
@braucht_recht(Recht.ANSEHEN)
def zurueck():
    dienst.zurueck(current_user)
    return _zum_schritt()


@bp.get("/schritt")
@braucht_recht(Recht.ANSEHEN)
def schritt():
    """Zur Seite des aktuellen Schritts (falls man zwischendurch woanders war)."""
    return _zum_schritt()


@bp.post("/beenden")
@braucht_recht(Recht.ANSEHEN)
def beenden():
    dienst.beende(current_user)
    flash("Rundgang beendet. Du findest ihn im Profil wieder.")
    return redirect(url_for("allgemein.start"))


@bp.post("/einstellen")
@braucht_recht(Recht.ANSEHEN)
def einstellen():
    stufe = request.form.get("erfahrung", "")
    if stufe not in STUFEN:
        flash("Bitte eine Stufe wählen.")
        return redirect(url_for("profil.profil") + "#rundgang")
    dienst.stelle_ein(current_user, stufe, request.form.get("kennt_steuy") == "ja")
    if request.form.get("aktion") == "starten":
        dienst.starte(current_user)
        return _zum_schritt()
    flash("Gespeichert.")
    return redirect(url_for("profil.profil") + "#rundgang")
