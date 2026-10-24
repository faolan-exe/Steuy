from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.domain.rollen import Recht
from app.extensions import db
from app.models import ShopBestellung
from app.services.einrichtung import aktuelles_gewerbe
from app.services.protokoll import protokolliere
from app.services.shop import (
    ShopFehler,
    eingerichtet,
    freigeben,
    speichere_einstellungen,
    synchronisiere,
    teste_verbindung,
)
from app.web.formulare import ShopFormular
from app.web.rechte import braucht_recht

bp = Blueprint("shop", __name__)


@bp.route("/einstellungen/shop", methods=["GET", "POST"])
@braucht_recht(Recht.EINSTELLUNGEN)
def einstellungen():
    gewerbe = aktuelles_gewerbe()
    formular = ShopFormular(obj=gewerbe)
    if request.method == "GET":
        formular.shop_schluessel.data = formular.shop_geheimnis.data = ""
    if formular.validate_on_submit():
        try:
            geaendert = speichere_einstellungen(
                gewerbe, {**formular.data, "trennen": request.form.get("trennen")}, current_user.id
            )
        except ShopFehler as fehler:
            db.session.rollback()
            formular.shop_url.errors = [*formular.shop_url.errors, str(fehler)]
        else:
            flash("Gespeichert." if geaendert else "Keine Änderungen.")
            return redirect(url_for("shop.einstellungen"))
    letzte = db.session.execute(
        db.select(ShopBestellung).order_by(ShopBestellung.aktualisiert_am.desc()).limit(10)
    ).scalars()
    return render_template(
        "shop_einstellungen.html",
        formular=formular,
        eingerichtet=eingerichtet(),
        g_=gewerbe,
        letzte=list(letzte),
    )


@bp.post("/einstellungen/shop/test")
@braucht_recht(Recht.EINSTELLUNGEN)
def verbindung_testen():
    try:
        teste_verbindung()
    except ShopFehler as fehler:
        flash(f"Verbindung fehlgeschlagen: {fehler}")
    else:
        flash("Verbindung zum Shop klappt.")
    return redirect(url_for("shop.einstellungen"))


@bp.post("/shop/abrufen")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def abrufen():
    try:
        ergebnis = synchronisiere(current_user.id)
    except ShopFehler as fehler:
        flash(f"Abruf fehlgeschlagen: {fehler}")
    else:
        flash(ergebnis.text())
        for meldung in ergebnis.fehler[:5]:
            flash(meldung)
    return redirect(request.form.get("zurueck") or url_for("allgemein.pruefen"))


def _eintrag(eintrag_id: int) -> ShopBestellung:
    eintrag = db.session.get(ShopBestellung, eintrag_id)
    if not eintrag:
        abort(404)
    return eintrag


@bp.post("/shop/<int:eintrag_id>/freigeben")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def freigabe(eintrag_id: int):
    eintrag = _eintrag(eintrag_id)
    try:
        meldungen = freigeben(eintrag, current_user.id)
    except ShopFehler as fehler:
        flash(str(fehler))
        if eintrag.rechnung_id:
            return redirect(url_for("rechnungen.bearbeiten", rechnung_id=eintrag.rechnung_id))
    else:
        for meldung in meldungen:
            flash(meldung)
    return redirect(url_for("allgemein.pruefen") + "#shop")


@bp.post("/shop/<int:eintrag_id>/erledigt")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def hinweis_erledigt(eintrag_id: int):
    eintrag = _eintrag(eintrag_id)
    eintrag.hinweis_erledigt_von = current_user.id
    protokolliere(
        "shop_hinweis_erledigt",
        nutzer_id=current_user.id,
        details={"bestellung": eintrag.nummer, "hinweis": eintrag.hinweis},
    )
    db.session.commit()
    flash(f"Hinweis zu Bestellung {eintrag.nummer} erledigt.")
    return redirect(url_for("allgemein.pruefen") + "#shop")
