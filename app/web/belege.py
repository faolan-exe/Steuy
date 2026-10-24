from datetime import date
from urllib.parse import quote

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import select

from app.domain.geld import cent_zu_euro
from app.domain.rollen import Recht
from app.domain.zahlung import ZAHLUNGSARTEN, ZahlungUngueltig
from app.extensions import db
from app.models import Beleg, Buchung, Kontakt
from app.services import ablage
from app.services.ablage import AblageBeschaedigt
from app.services.anlagen import abschreibung_sinnvoll, ueber_gwg_grenze
from app.services.belege import (
    BelegUngueltig,
    BelegVorhanden,
    lade_hoch,
    neue_belege,
    verwerfe,
    vorschlag_fuer_formular,
)
from app.services.buchungen import (
    Buchungsdaten,
    BuchungUngueltig,
    aendere_entwurf,
    erfasse_gebuehren,
    erfasse_zahlung,
    festschreiben,
    kategorien,
    lege_entwurf_an,
    loesche_entwurf,
    offene_gebuehren,
    pruefe_festschreibbar,
    storniere,
    suche_buchungen,
)
from app.services.rechte import darf
from app.web.formulare import BuchungFormular, BuchungsZahlungFormular
from app.web.rechte import braucht_recht

bp = Blueprint("belege", __name__)

FILTER = {
    "pruefen": "Zu prüfen",
    "ausgaben": "Ausgaben",
    "einnahmen": "Einnahmen",
    "entwuerfe": "Entwürfe",
    "verworfen": "Verworfen",
}
GWG_HINWEIS_AB_CENT = 95200  # 800 € netto bei 19 % (docs/domain/euer.md)


def _beleg(beleg_id: int) -> Beleg:
    return db.session.get(Beleg, beleg_id) or abort(404)


def _buchung(buchung_id: int) -> Buchung:
    return db.session.get(Buchung, buchung_id) or abort(404)


def _formular(**vorbelegung) -> BuchungFormular:
    formular = BuchungFormular(**vorbelegung)
    kontakte = db.session.execute(select(Kontakt).where(Kontakt.archiviert.is_(False))).scalars()
    formular.kontakt_id.choices = [("", "– kein Kontakt –")] + [
        (str(k.id), k.name) for k in sorted(kontakte, key=lambda k: k.name.lower())
    ]
    formular.kategorie_id.choices = [("", "– bitte wählen –")] + [
        (str(k.id), f"{'Einnahme' if k.art == 'einnahme' else 'Ausgabe'}: {k.name}")
        for k in kategorien()
    ]
    return formular


def _daten(formular: BuchungFormular, beleg_id: int | None) -> Buchungsdaten:
    kontakt_id = int(formular.kontakt_id.data) if formular.kontakt_id.data else None
    partner = (formular.partner.data or "").strip() or None
    if kontakt_id and not partner:
        partner = db.session.get(Kontakt, kontakt_id).name
    return Buchungsdaten(
        art=formular.art.data,
        belegdatum=formular.belegdatum.data,
        betrag_cent=formular.betrag_cent,
        kategorie_id=int(formular.kategorie_id.data) if formular.kategorie_id.data else None,
        betrieblich_prozent=formular.betrieblich_prozent.data,
        kontakt_id=kontakt_id,
        partner=partner,
        belegnummer=(formular.belegnummer.data or "").strip() or None,
        beschreibung=(formular.beschreibung.data or "").strip() or None,
        beleg_id=beleg_id,
    )


def _speichern(formular: BuchungFormular, buchung: Buchung | None, beleg_id: int | None):
    """Speichert den Entwurf und schreibt bei aktion=festschreiben direkt fest."""
    daten = _daten(formular, beleg_id)
    bezahlt_am = formular.bezahlt_am.data if formular.bereits_bezahlt.data else None
    festschreiben_gewuenscht = request.form.get("aktion") == "festschreiben"
    if festschreiben_gewuenscht and darf(current_user, Recht.BUCHEN):
        pruefe_festschreibbar(daten, bezahlt_am)
    if buchung is None:
        buchung = lege_entwurf_an(daten, current_user.id)
    else:
        aendere_entwurf(buchung, daten)
    if festschreiben_gewuenscht:
        if not darf(current_user, Recht.BUCHEN):
            flash("Als Entwurf gespeichert. Festschreiben darf deine Rolle nicht.")
            return redirect(url_for("belege.buchung", buchung_id=buchung.id))
        festschreiben(
            buchung,
            current_user.id,
            bezahlt_am=bezahlt_am,
            zahlungsart=formular.zahlungsart.data,
        )
        flash("Buchung festgeschrieben.")
        if ueber_gwg_grenze(buchung):
            flash(
                "Diese Anschaffung liegt über der Grenze für geringwertige Wirtschaftsgüter "
                "(800 € netto). Sie zählt deshalb nicht einfach als Ausgabe: Je nach Art wird sie "
                "sofort voll (Computer, Software) oder über mehrere Jahre abgeschrieben."
            )
            return redirect(url_for("anlagen.anlegen", buchung_id=buchung.id))
    else:
        flash("Entwurf gespeichert.")
    return redirect(url_for("belege.buchung", buchung_id=buchung.id))


def _formularseite(formular, beleg=None, buchung=None, hinweis=None, status=200):
    betrag = formular.betrag_cent or 0
    return render_template(
        "buchung_formular.html",
        formular=formular,
        beleg=beleg,
        buchung=buchung,
        hinweis=hinweis,
        gwg_hinweis=formular.art.data == "ausgabe" and betrag >= GWG_HINWEIS_AB_CENT,
    ), status


# ---------- Liste und Upload ----------


@bp.get("/belege")
@braucht_recht(Recht.ANSEHEN)
def liste():
    neue = neue_belege()
    filter = request.args.get("filter") or ("pruefen" if neue else "ausgaben")
    filter = filter if filter in FILTER else "ausgaben"
    belege, buchungen = [], []
    if filter == "pruefen":
        belege = neue
    elif filter == "verworfen":
        belege = list(
            db.session.execute(
                select(Beleg).where(Beleg.verworfen).order_by(Beleg.hochgeladen_am.desc())
            ).scalars()
        )
    else:
        buchungen = suche_buchungen(filter)
    return render_template(
        "belege.html",
        filter=filter,
        filter_namen=FILTER,
        belege=belege,
        buchungen=buchungen,
        anzahl_neu=len(neue),
    )


@bp.post("/belege/hochladen")
@braucht_recht(Recht.BELEGE)
def hochladen():
    dateien = [d for d in request.files.getlist("dateien") if d and d.filename]
    if not dateien:
        flash("Bitte mindestens eine Datei auswählen.")
        return redirect(url_for("belege.liste"))
    neu = []
    for datei in dateien:
        try:
            neu.append(lade_hoch(datei.filename, datei.read(), current_user.id))
        except BelegVorhanden as fehler:
            db.session.rollback()
            flash(str(fehler))
        except BelegUngueltig as fehler:
            db.session.rollback()
            flash(str(fehler))
    if len(neu) == 1:
        return redirect(url_for("belege.beleg", beleg_id=neu[0].id))
    if neu:
        flash(f"{len(neu)} Belege hochgeladen.")
    return redirect(url_for("belege.liste", filter="pruefen"))


# ---------- Beleg ----------


@bp.get("/belege/<int:beleg_id>/datei")
@braucht_recht(Recht.ANSEHEN)
def datei(beleg_id: int):
    beleg = _beleg(beleg_id)
    try:
        inhalt = ablage.lies(beleg.sha256)
    except AblageBeschaedigt:
        abort(500, "Die abgelegte Datei wurde verändert. Bitte aus dem Backup wiederherstellen.")
    # XML als Text ausliefern, damit der Browser nichts darin ausführt.
    mime = "text/plain; charset=utf-8" if beleg.mime == "application/xml" else beleg.mime
    headers = {
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(beleg.dateiname)}",
        "X-Content-Type-Options": "nosniff",
    }
    if beleg.mime != "application/pdf":
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'"
    return Response(inhalt, mimetype=mime, headers=headers)


@bp.route("/belege/<int:beleg_id>", methods=["GET", "POST"])
@braucht_recht(Recht.ANSEHEN)
def beleg(beleg_id: int):
    beleg = _beleg(beleg_id)
    aktive = [b for b in beleg.buchungen if b.storno_von_id is None and not b.storniert]
    if aktive:
        if request.method == "POST":
            flash("Zu diesem Beleg gibt es schon eine Buchung.")
        return redirect(url_for("belege.buchung", buchung_id=aktive[0].id))

    vorschlag = vorschlag_fuer_formular(beleg)
    if request.method == "GET":
        vorbelegung = {
            "belegdatum": vorschlag.get("belegdatum") or date.today(),
            "belegnummer": vorschlag.get("belegnummer"),
            "partner": vorschlag.get("partner"),
            "kontakt_id": str(vorschlag.get("kontakt_id") or ""),
            "betrag": cent_zu_euro(vorschlag["betrag_cent"])[:-2]
            if vorschlag.get("betrag_cent")
            else "",
            # Belege mit Karte oder bar sind meist am Belegtag bezahlt
            "bezahlt_am": vorschlag.get("belegdatum") or date.today(),
        }
        formular = _formular(**vorbelegung)
        formular.betrag_cent = vorschlag.get("betrag_cent")
        hinweis = vorschlag.get("hinweis")
        if vorschlag.get("quelle"):
            quelle = {
                "xrechnung": "der XRechnung",
                "zugferd": "der ZUGFeRD-Rechnung",
                "text": "dem PDF-Text",
                "ocr": "der Texterkennung",
            }.get(vorschlag["quelle"], "dem Beleg")
            hinweis = f"Felder aus {quelle} vorausgefüllt. Bitte prüfen." + (
                f" {hinweis}" if hinweis else ""
            )
        return _formularseite(formular, beleg=beleg, hinweis=hinweis)

    if not darf(current_user, Recht.BELEGE):
        abort(403)
    formular = _formular()
    if formular.validate_on_submit():
        try:
            return _speichern(formular, None, beleg.id)
        except (BuchungUngueltig, ZahlungUngueltig) as fehler:
            db.session.rollback()
            formular.kategorie_id.errors.append(str(fehler))
    return _formularseite(formular, beleg=beleg, status=422)


@bp.post("/belege/<int:beleg_id>/verwerfen")
@braucht_recht(Recht.BELEGE)
def verwerfen(beleg_id: int):
    try:
        verwerfe(_beleg(beleg_id), current_user.id)
    except BelegUngueltig as fehler:
        flash(str(fehler))
        return redirect(url_for("belege.beleg", beleg_id=beleg_id))
    flash("Beleg verworfen. Die Datei bleibt im Archiv erhalten.")
    return redirect(url_for("belege.liste"))


# ---------- Buchungen ----------


@bp.route("/buchungen/neu", methods=["GET", "POST"])
@braucht_recht(Recht.BELEGE)
def neue_buchung():
    formular = _formular(belegdatum=date.today(), bezahlt_am=date.today())
    if request.method == "POST" and formular.validate_on_submit():
        try:
            return _speichern(formular, None, None)
        except (BuchungUngueltig, ZahlungUngueltig) as fehler:
            db.session.rollback()
            formular.kategorie_id.errors.append(str(fehler))
    status = 422 if request.method == "POST" else 200
    return _formularseite(formular, status=status)


@bp.route("/buchungen/<int:buchung_id>", methods=["GET", "POST"])
@braucht_recht(Recht.ANSEHEN)
def buchung(buchung_id: int):
    buchung = _buchung(buchung_id)
    if not buchung.ist_entwurf:
        offen = buchung.offen_cent
        zahlformular = BuchungsZahlungFormular(
            datum=date.today(), betrag=cent_zu_euro(offen)[:-2] if offen > 0 else ""
        )
        return render_template(
            "buchung.html",
            b=buchung,
            zahlformular=zahlformular,
            zahlungsarten=ZAHLUNGSARTEN,
            abschreibbar=abschreibung_sinnvoll(buchung),
        )

    if request.method == "GET":
        formular = _formular(
            obj=buchung,
            kontakt_id=str(buchung.kontakt_id or ""),
            kategorie_id=str(buchung.kategorie_id or ""),
            betrag=cent_zu_euro(buchung.betrag_cent)[:-2],
            bezahlt_am=date.today(),
        )
        formular.betrag_cent = buchung.betrag_cent
        return _formularseite(formular, beleg=buchung.beleg, buchung=buchung)

    if not darf(current_user, Recht.BELEGE):
        abort(403)
    formular = _formular()
    if formular.validate_on_submit():
        try:
            return _speichern(formular, buchung, buchung.beleg_id)
        except (BuchungUngueltig, ZahlungUngueltig) as fehler:
            db.session.rollback()
            formular.kategorie_id.errors.append(str(fehler))
    return _formularseite(formular, beleg=buchung.beleg, buchung=buchung, status=422)


@bp.post("/buchungen/<int:buchung_id>/loeschen")
@braucht_recht(Recht.BELEGE)
def buchung_loeschen(buchung_id: int):
    buchung = _buchung(buchung_id)
    beleg_id = buchung.beleg_id
    try:
        loesche_entwurf(buchung, current_user.id)
    except BuchungUngueltig:
        abort(409)
    flash("Entwurf gelöscht.")
    if beleg_id:
        return redirect(url_for("belege.beleg", beleg_id=beleg_id))
    return redirect(url_for("belege.liste"))


@bp.post("/buchungen/<int:buchung_id>/stornieren")
@braucht_recht(Recht.BUCHEN)
def buchung_stornieren(buchung_id: int):
    try:
        storniere(_buchung(buchung_id), current_user.id)
    except BuchungUngueltig as fehler:
        flash(str(fehler))
    else:
        flash("Buchung storniert. Der Beleg kann neu verbucht werden.")
    return redirect(url_for("belege.buchung", buchung_id=buchung_id))


@bp.get("/buchungen/<int:buchung_id>/zahlungen")
@braucht_recht(Recht.ANSEHEN)
def buchung_zahlung_get(buchung_id: int):
    """Neuladen nach einem Fehler beim Erfassen: zurück zur Buchung statt Fehlerseite."""
    return redirect(url_for("belege.buchung", buchung_id=buchung_id) + "#zahlungen")


@bp.post("/buchungen/<int:buchung_id>/zahlungen")
@braucht_recht(Recht.ZAHLUNGEN)
def buchung_zahlung(buchung_id: int):
    buchung = _buchung(buchung_id)
    formular = BuchungsZahlungFormular()
    if formular.validate_on_submit():
        try:
            erfasse_zahlung(
                buchung,
                datum=formular.datum.data,
                betrag_cent=formular.betrag_cent,
                zahlungsart=formular.zahlungsart.data,
                notiz=formular.notiz.data,
                nutzer_id=current_user.id,
            )
        except ZahlungUngueltig as fehler:
            db.session.rollback()
            formular.betrag.errors.append(str(fehler))
        else:
            flash("Zahlung erfasst.")
            return redirect(url_for("belege.buchung", buchung_id=buchung.id))
    return render_template(
        "buchung.html",
        b=buchung,
        zahlformular=formular,
        zahlungsarten=ZAHLUNGSARTEN,
        abschreibbar=abschreibung_sinnvoll(buchung),
    ), 422


@bp.route("/buchungen/gebuehren", methods=["GET", "POST"])
@braucht_recht(Recht.BUCHEN)
def gebuehren():
    if request.method == "POST":
        ids = [int(i) for i in request.form.getlist("zahlung") if i.isdigit()]
        try:
            buchung = erfasse_gebuehren(ids, current_user.id)
        except BuchungUngueltig as fehler:
            db.session.rollback()
            flash(str(fehler))
        else:
            flash(f"Gebühren über {cent_zu_euro(buchung.betrag_cent)} als Ausgabe gebucht.")
            return redirect(url_for("belege.buchung", buchung_id=buchung.id))
    return render_template("gebuehren.html", zahlungen=offene_gebuehren())


@bp.post("/jahreswechsel/<int:zahlung_id>")
@braucht_recht(Recht.BUCHEN)
def jahreswechsel(zahlung_id: int):
    from app.models import Zahlung
    from app.services.jahreswechsel import ZuordnungUngueltig, bestaetige

    zahlung = db.session.get(Zahlung, zahlung_id)
    if not zahlung or not zahlung.buchung_id:
        abort(404)
    wert = request.form.get("jahr", "")
    try:
        bestaetige(zahlung, int(wert) if wert.isdigit() else 0, current_user.id)
    except ZuordnungUngueltig as fehler:
        flash(str(fehler))
    else:
        flash(f"Zahlung vom {zahlung.datum:%d.%m.%Y} zählt in der EÜR {wert}.")
    return redirect(url_for("allgemein.pruefen") + "#jahreswechsel")
