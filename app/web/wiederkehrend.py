"""Wiederkehrende Rechnungen: Liste, Editor, Pausieren und sofort erzeugen."""

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.domain.rollen import Recht
from app.domain.wiederkehrend import INTERVALL_NAMEN, VERSAND_ARTEN
from app.extensions import db
from app.models import Artikel, Kontakt, Rechnung, WiederkehrendeRechnung
from app.services import mail, wiederkehrend
from app.services.einrichtung import aktuelles_gewerbe
from app.services.rechte import darf
from app.web.rechnungseditor import lies_formular, roh_aus_rechnung, wende_positionsaktion
from app.web.rechte import braucht_recht

bp = Blueprint("wiederkehrend", __name__, url_prefix="/wiederkehrend")


def _vorlage(vorlage_id: int) -> WiederkehrendeRechnung:
    return db.session.get(WiederkehrendeRechnung, vorlage_id) or abort(404)


def _auswahl() -> dict:
    kunden = db.session.execute(
        select(Kontakt).where(Kontakt.ist_kunde, Kontakt.archiviert.is_(False))
    ).scalars()
    artikel = db.session.execute(
        select(Artikel).where(Artikel.archiviert.is_(False)).order_by(Artikel.bezeichnung)
    ).scalars()
    return {
        "kunden": sorted(kunden, key=lambda k: k.name.lower()),
        "artikelliste": list(artikel),
        "intervalle": INTERVALL_NAMEN,
        "versand_arten": VERSAND_ARTEN,
        "gewerbe": aktuelles_gewerbe(),
        "mail_da": mail.eingerichtet(),
    }


@bp.get("")
@braucht_recht(Recht.ANSEHEN)
def liste():
    return render_template(
        "wiederkehrend.html",
        vorlagen=wiederkehrend.alle(),
        intervalle=INTERVALL_NAMEN,
        versand_arten=VERSAND_ARTEN,
        heute=date.today(),
    )


@bp.post("/neu")
@braucht_recht(Recht.ENTWUERFE)
def neu():
    vorlage = wiederkehrend.lege_leer_an(current_user.id)
    return redirect(url_for("wiederkehrend.bearbeiten", vorlage_id=vorlage.id))


@bp.post("/aus-rechnung/<int:rechnung_id>")
@braucht_recht(Recht.ENTWUERFE)
def aus_rechnung(rechnung_id: int):
    rechnung = db.session.get(Rechnung, rechnung_id) or abort(404)
    try:
        vorlage = wiederkehrend.lege_aus_rechnung_an(rechnung, current_user.id)
    except wiederkehrend.VorlageUngueltig as fehler:
        flash(str(fehler))
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id))
    flash("Vorlage angelegt. Bitte Intervall und ersten Termin prüfen.")
    return redirect(url_for("wiederkehrend.bearbeiten", vorlage_id=vorlage.id))


def _einstellungen(formular, fehler: dict) -> wiederkehrend.Einstellungen:
    def datum(name: str, pflicht: bool) -> date | None:
        wert = (formular.get(name) or "").strip()
        if not wert:
            if pflicht:
                fehler[name] = "Pflichtfeld"
            return None
        try:
            return date.fromisoformat(wert)
        except ValueError:
            fehler[name] = "Ungültiges Datum."
            return None

    versand = formular.get("versand", "entwurf")
    if versand != "entwurf" and not darf(current_user, Recht.RECHNUNGEN_VERSENDEN):
        fehler["versand"] = "Dafür fehlt dir das Recht zum Versenden."
    return wiederkehrend.Einstellungen(
        name=(formular.get("name") or "").strip(),
        intervall=formular.get("intervall", "monatlich"),
        naechste_am=datum("naechste_am", True) or date.today(),
        ende_am=datum("ende_am", False),
        versand=versand,
        aktiv=formular.get("aktiv") == "y",
    )


@bp.route("/<int:vorlage_id>", methods=["GET", "POST"])
@braucht_recht(Recht.ANSEHEN)
def bearbeiten(vorlage_id: int):
    vorlage = _vorlage(vorlage_id)
    kann_aendern = darf(current_user, Recht.ENTWUERFE)
    if request.method == "GET" or not kann_aendern:
        if request.method == "POST":
            abort(403)
        return render_template(
            "wiederkehrend_editor.html",
            r=vorlage,
            positionen=roh_aus_rechnung(vorlage),
            fehler={},
            rechnungen=wiederkehrend.rechnungen_der_vorlage(vorlage),
            kann_aendern=kann_aendern,
            heute=date.today(),
            **_auswahl(),
        )

    eingabe = lies_formular(request.form)
    fehler = dict(eingabe.fehler)
    einstellungen = _einstellungen(request.form, fehler)
    try:
        wiederkehrend.pruefe_einstellungen(einstellungen)
    except wiederkehrend.VorlageUngueltig as problem:
        fehler["einstellung"] = str(problem)
    if fehler:
        return render_template(
            "wiederkehrend_editor.html",
            r=vorlage,
            positionen=eingabe.roh,
            fehler=fehler,
            rechnungen=wiederkehrend.rechnungen_der_vorlage(vorlage),
            kann_aendern=kann_aendern,
            heute=date.today(),
            **_auswahl(),
        ), 422

    aktion = request.form.get("aktion", "speichern")
    positionen = wende_positionsaktion(aktion, eingabe.positionen, request.form)
    wiederkehrend.speichere(vorlage, eingabe.kopf, positionen, einstellungen, current_user.id)
    if aktion == "speichern":
        flash("Gespeichert.")
        return redirect(url_for("wiederkehrend.liste"))
    return redirect(url_for("wiederkehrend.bearbeiten", vorlage_id=vorlage.id) + "#positionen")


@bp.post("/<int:vorlage_id>/pausieren")
@braucht_recht(Recht.ENTWUERFE)
def pausieren(vorlage_id: int):
    vorlage = _vorlage(vorlage_id)
    wiederkehrend.setze_aktiv(vorlage, False, current_user.id)
    flash("Pausiert: Es entstehen keine neuen Rechnungen.")
    return redirect(url_for("wiederkehrend.liste"))


@bp.post("/<int:vorlage_id>/fortsetzen")
@braucht_recht(Recht.ENTWUERFE)
def fortsetzen(vorlage_id: int):
    vorlage = _vorlage(vorlage_id)
    wiederkehrend.setze_aktiv(vorlage, True, current_user.id)
    flash("Fortgesetzt.")
    return redirect(url_for("wiederkehrend.liste"))


@bp.post("/<int:vorlage_id>/jetzt")
@braucht_recht(Recht.ENTWUERFE)
def jetzt(vorlage_id: int):
    vorlage = _vorlage(vorlage_id)
    try:
        rechnung, _ = wiederkehrend.erzeuge_jetzt(vorlage, current_user.id)
    except wiederkehrend.VorlageUngueltig as fehler:
        flash(str(fehler))
        return redirect(url_for("wiederkehrend.liste"))
    flash("Rechnungsentwurf angelegt. Der nächste Termin ist weitergerückt.")
    return redirect(url_for("rechnungen.bearbeiten", rechnung_id=rechnung.id))


@bp.post("/<int:vorlage_id>/loeschen")
@braucht_recht(Recht.ENTWUERFE)
def loeschen(vorlage_id: int):
    vorlage = _vorlage(vorlage_id)
    try:
        wiederkehrend.loesche(vorlage, current_user.id)
    except wiederkehrend.VorlageUngueltig as fehler:
        flash(str(fehler))
        return redirect(url_for("wiederkehrend.bearbeiten", vorlage_id=vorlage.id))
    flash("Vorlage gelöscht.")
    return redirect(url_for("wiederkehrend.liste"))


@bp.post("/lauf")
@braucht_recht(Recht.ENTWUERFE)
def lauf():
    ergebnis = wiederkehrend.fuehre_aus(current_user.id)
    flash(ergebnis.text())
    for name, hinweis in ergebnis.probleme:
        flash(f"{name}: {hinweis}")
    return redirect(url_for("wiederkehrend.liste"))
