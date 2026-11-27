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
from app.domain.mahnung import (
    PAUSCHALE_AB_STUFE,
    PLATZHALTER,
    TEXT_MAX,
    VERZUGSPAUSCHALE_CENT,
)
from app.domain.rollen import Recht
from app.domain.zahlung import ZAHLUNGSARTEN, ZahlungUngueltig, offene_gebuehr
from app.extensions import db
from app.models import LEISTUNG_ARTEN, Artikel, Kontakt, Mahnung, Rechnung, Zahlung
from app.services import ablage
from app.services.ablage import AblageBeschaedigt
from app.services.einrichtung import aktuelles_gewerbe
from app.services.mahnwesen import (
    MahnungNichtMoeglich,
    MahnungSchonErstellt,
    entwurf,
    erstelle_mahnung,
    ist_neueste,
    ist_verschickt,
    loeschbar,
    loesche_mahnung,
    naechste_faellig_ab,
    naechste_fuer,
    pauschale_vorschlag,
    pruefe_mahnbar,
    setze_mahnsperre,
    speichere_vorlage,
    stufentext,
    ziehe_zurueck,
)
from app.services.mahnwesen import (
    stufen as mahnstufen,
)
from app.services.mahnwesen import (
    vorlagen as mahnvorlagen,
)
from app.services.mail import MailFehler
from app.services.mail import eingerichtet as mail_eingerichtet
from app.services.pdf import rendere_mahnung
from app.services.rechnungen import (
    AktionNichtMoeglich,
    NichtBearbeitbar,
    NichtFinalisierbar,
    belegkette,
    empfaenger_aus_kontakt,
    entscheide_angebot,
    ergaenze_reverse_charge,
    finalisiere,
    finalisierungsfehler,
    lieferschein_aus_rechnung,
    lieferscheine_zu,
    loesche_entwurf,
    neuer_entwurf,
    oeffne_angebot,
    pdf,
    pruefhinweise,
    rechnung_aus_angebot,
    rechnungen_zum_angebot,
    reverse_charge_vorschlag,
    speichere_entwurf,
    storniere_rechnung,
    suche_rechnungen,
)
from app.services.rechte import darf
from app.services.versand import dateiname, sende_beleg, vorschlag
from app.services.zahlungen import erfasse_zahlung, ist_storniert, storniere_zahlung
from app.web.formulare import SendenFormular, ZahlungFormular
from app.web.rechnungseditor import (
    Ansicht,
    entwurfsstand,
    lies_formular,
    ohne_leere,
    roh_aus_rechnung,
    wende_positionsaktion,
)
from app.web.rechte import braucht_recht

bp = Blueprint("rechnungen", __name__, url_prefix="/rechnungen")
angebote_bp = Blueprint("angebote", __name__, url_prefix="/angebote")

FILTER = {"alle": "Alle", "entwuerfe": "Entwürfe", "offen": "Offen", "ueberfaellig": "Überfällig"}


def _rechnung(rechnung_id: int) -> Rechnung:
    return db.session.get(Rechnung, rechnung_id) or abort(404)


def _anschrift_geaendert(rechnung: Rechnung) -> bool:
    """Wurde die Anschrift im Kontakt geändert, seit der Entwurf sie übernommen hat?"""
    k = rechnung.kontakt
    if k is None or k.archiviert:
        return False
    return any(
        (getattr(rechnung, feld) or "").strip() != (wert or "").strip()
        for feld, wert in empfaenger_aus_kontakt(k).items()
        if feld != "empfaenger_name"
    )


def _auswahl():
    kunden = db.session.execute(
        select(Kontakt).where(Kontakt.ist_kunde, Kontakt.archiviert.is_(False))
    ).scalars()
    artikel = db.session.execute(
        select(Artikel).where(Artikel.archiviert.is_(False)).order_by(Artikel.bezeichnung)
    ).scalars()
    kunden = sorted(kunden, key=lambda k: k.name.lower())
    # Zuletzt verwendete Kunden oben, damit man bei vielen Kontakten nicht suchen muss
    letzte_ids = []
    for kontakt_id in db.session.execute(
        select(Rechnung.kontakt_id)
        .where(Rechnung.kontakt_id.is_not(None))
        .order_by(Rechnung.erstellt_am.desc())
        .limit(50)
    ).scalars():
        if kontakt_id not in letzte_ids:
            letzte_ids.append(kontakt_id)
        if len(letzte_ids) == 5:
            break
    nach_id = {k.id: k for k in kunden}
    return {
        "kunden": kunden,
        "zuletzt": [nach_id[i] for i in letzte_ids if i in nach_id] if len(kunden) > 8 else [],
        "artikelliste": list(artikel),
        "leistung_arten": LEISTUNG_ARTEN,
    }


def _liste(angebote: bool):
    filter = request.args.get("filter", "alle")
    filter = filter if filter in FILTER else "alle"
    return render_template(
        "rechnungen.html",
        rechnungen=suche_rechnungen(filter, angebote=angebote),
        filter=filter,
        filter_namen={**FILTER, "ueberfaellig": "Abgelaufen"} if angebote else FILTER,
        angebote=angebote,
    )


@bp.get("")
@braucht_recht(Recht.ANSEHEN)
def liste():
    return _liste(angebote=False)


@angebote_bp.get("")
@braucht_recht(Recht.ANSEHEN)
def angebote():
    return _liste(angebote=True)


def _kontakt_aus_anfrage() -> Kontakt | None:
    wert = request.form.get("kontakt_id", "")
    kontakt = db.session.get(Kontakt, int(wert)) if wert.isdigit() else None
    return kontakt if kontakt and kontakt.ist_kunde and not kontakt.archiviert else None


@bp.post("/neu")
@braucht_recht(Recht.ENTWUERFE)
def neu():
    rechnung = neuer_entwurf(current_user.id, kontakt=_kontakt_aus_anfrage())
    return redirect(url_for("rechnungen.bearbeiten", rechnung_id=rechnung.id))


@angebote_bp.post("/neu")
@braucht_recht(Recht.ENTWUERFE)
def angebot_neu():
    angebot = neuer_entwurf(current_user.id, "angebot", kontakt=_kontakt_aus_anfrage())
    return redirect(url_for("rechnungen.bearbeiten", rechnung_id=angebot.id))


@bp.get("/<int:rechnung_id>")
@braucht_recht(Recht.ANSEHEN)
def detail(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    if rechnung.ist_entwurf and darf(current_user, Recht.ENTWUERFE):
        return redirect(url_for("rechnungen.bearbeiten", rechnung_id=rechnung.id))
    return _detailseite(rechnung, ZahlungFormular(betrag=_als_text(rechnung.offen_cent)))


def _als_text(cent: int) -> str:
    return cent_zu_euro(cent)[:-2]


def _detailseite(rechnung: Rechnung, formular: ZahlungFormular, status: int = 200):
    if formular.datum.data is None and not formular.errors:
        formular.datum.data = date.today()
    return render_template(
        "rechnung.html",
        r=rechnung,
        formular=formular,
        zahlungsarten=ZAHLUNGSARTEN,
        ist_storniert=ist_storniert,
        offene_gebuehr=offene_gebuehr,
        kette=belegkette(rechnung),
        rechnung_aus_angebot_vorhanden=bool(
            rechnung.belegart == "angebot" and rechnungen_zum_angebot(rechnung)
        ),
        lieferscheine=lieferscheine_zu(rechnung) if rechnung.ist_rechnung else [],
        naechste_mahnstufe=naechste_fuer(rechnung) if rechnung.offen_cent > 0 else None,
        mahnstufe_ab=naechste_faellig_ab(rechnung) if rechnung.offen_cent > 0 else None,
        heute=date.today(),
        portal=_portal(rechnung),
    ), status


def _portal(rechnung: Rechnung) -> dict:
    from app.services import kundenportal

    link = None if rechnung.ist_entwurf else kundenportal.aktueller_link(rechnung)
    gewerbe = aktuelles_gewerbe()
    return {
        "eingeschaltet": bool(gewerbe and gewerbe.kundenportal),
        "adresse": kundenportal.oeffentliche_adresse(),
        "link": link,
        "url": kundenportal.url(link) if link else None,
    }


@bp.post("/<int:rechnung_id>/kundenlink")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def kundenlink_neu(rechnung_id: int):
    """Link erzeugen oder (falls schon einer besteht) sperren und durch einen neuen ersetzen."""
    from app.services import kundenportal

    rechnung = _rechnung(rechnung_id)
    try:
        kundenportal.neuer_link(rechnung, current_user.id)
    except kundenportal.PortalFehler as fehler:
        flash(str(fehler))
    else:
        db.session.commit()
        flash("Neuer Kundenlink erzeugt.")
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id) + "#kundenlink")


@bp.get("/<int:rechnung_id>/zahlungen")
@braucht_recht(Recht.ANSEHEN)
def zahlung_erfassen_get(rechnung_id: int):
    """Neuladen nach einem Fehler beim Erfassen: zurück zur Rechnung statt Fehlerseite."""
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id) + "#zahlungen")


@bp.post("/<int:rechnung_id>/zahlungen")
@braucht_recht(Recht.ZAHLUNGEN)
def zahlung_erfassen(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    formular = ZahlungFormular()
    if formular.validate_on_submit():
        try:
            erfasse_zahlung(
                rechnung,
                datum=formular.datum.data,
                betrag_cent=formular.betrag_cent,
                zahlungsart=formular.zahlungsart.data,
                angekommen_cent=formular.angekommen_cent,
                notiz=formular.notiz.data,
                nutzer_id=current_user.id,
                referenz=formular.referenz.data,
                nachweis=_datei(formular.nachweis.data),
            )
        except ZahlungUngueltig as fehler:
            db.session.rollback()
            ziel = formular.nachweis if "Nachweis" in str(fehler) else formular.betrag
            ziel.errors = [*ziel.errors, str(fehler)]
        else:
            flash("Zahlung erfasst.")
            return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id))
    return _detailseite(rechnung, formular, 422)


def _datei(datei) -> tuple[str, bytes] | None:
    if not datei or not getattr(datei, "filename", ""):
        return None
    return datei.filename, datei.read()


def _zahlung(rechnung_id: int, zahlung_id: int) -> Zahlung:
    zahlung = db.session.get(Zahlung, zahlung_id)
    if not zahlung or zahlung.rechnung_id != rechnung_id:
        abort(404)
    return zahlung


@bp.get("/<int:rechnung_id>/zahlungen/<int:zahlung_id>")
@braucht_recht(Recht.ANSEHEN)
def zahlung_detail(rechnung_id: int, zahlung_id: int):
    zahlung = _zahlung(rechnung_id, zahlung_id)
    return render_template(
        "zahlung.html",
        z=zahlung,
        r=zahlung.rechnung,
        zahlungsarten=ZAHLUNGSARTEN,
        ist_storniert=ist_storniert,
        offene_gebuehr=offene_gebuehr,
    )


@bp.get("/<int:rechnung_id>/zahlungen/<int:zahlung_id>/nachweis")
@braucht_recht(Recht.ANSEHEN)
def zahlung_nachweis(rechnung_id: int, zahlung_id: int):
    zahlung = _zahlung(rechnung_id, zahlung_id)
    if not zahlung.nachweis_sha256:
        abort(404)
    name = quote(zahlung.nachweis_name or "nachweis")
    return Response(
        ablage.lies(zahlung.nachweis_sha256),
        mimetype=zahlung.nachweis_mime,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{name}",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@bp.post("/<int:rechnung_id>/zahlungen/<int:zahlung_id>/rueckgaengig")
@braucht_recht(Recht.ZAHLUNGEN)
def zahlung_rueckgaengig(rechnung_id: int, zahlung_id: int):
    zahlung = _zahlung(rechnung_id, zahlung_id)
    try:
        storniere_zahlung(zahlung, current_user.id)
    except ZahlungUngueltig as fehler:
        flash(str(fehler))
    else:
        flash("Zahlung rückgängig gemacht.")
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id))


@bp.route("/<int:rechnung_id>/bearbeiten", methods=["GET", "POST"])
@braucht_recht(Recht.ENTWUERFE)
def bearbeiten(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    if not rechnung.ist_entwurf:
        flash("Diese Rechnung ist finalisiert und kann nicht mehr geändert werden.")
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id))

    if request.method == "GET":
        return render_template(
            "rechnung_editor.html",
            r=rechnung,
            positionen=roh_aus_rechnung(rechnung),
            fehler={},
            stand=entwurfsstand(rechnung),
            anschrift_geaendert=_anschrift_geaendert(rechnung),
            **_auswahl(),
        )

    eingabe = lies_formular(request.form)
    ansicht = Ansicht(rechnung, vars(eingabe.kopf) if eingabe.kopf else {})
    gesendet = request.form.get("stand")
    if gesendet and gesendet != entwurfsstand(rechnung):
        # Ein anderes Fenster hat inzwischen gespeichert: nicht still überschreiben
        return render_template(
            "rechnung_editor.html",
            r=ansicht,
            positionen=eingabe.roh,
            fehler={
                "stand": "Dieser Entwurf wurde inzwischen in einem anderen Fenster geändert. "
                "Unten stehen deine Eingaben, gespeichert ist noch nichts. Speichern übernimmt "
                "sie und ersetzt den anderen Stand."
            },
            stand=entwurfsstand(rechnung),
            **_auswahl(),
        ), 409
    if eingabe.fehler:
        return render_template(
            "rechnung_editor.html",
            r=ansicht,
            positionen=eingabe.roh,
            fehler=eingabe.fehler,
            stand=gesendet or entwurfsstand(rechnung),
            **_auswahl(),
        ), 422

    aktion = request.form.get("aktion", "speichern")
    positionen = wende_positionsaktion(aktion, eingabe.positionen, request.form)
    if aktion in ("speichern", "vorschau"):
        positionen = ohne_leere(positionen)

    vorher_kontakt = rechnung.kontakt_id
    speichere_entwurf(rechnung, eingabe.kopf, positionen)
    if vorher_kontakt is None and rechnung.kontakt_id and not eingabe.kopf.kontakt_id:
        flash(f"Mit dem vorhandenen Kontakt „{rechnung.kontakt.name}“ verbunden.")

    if aktion == "vorschau":
        return redirect(url_for("rechnungen.vorschau", rechnung_id=rechnung.id))
    if aktion == "speichern":
        flash("Entwurf gespeichert.")
    return redirect(url_for("rechnungen.bearbeiten", rechnung_id=rechnung.id) + "#positionen")


@bp.get("/<int:rechnung_id>/vorschau")
@braucht_recht(Recht.ENTWUERFE)
def vorschau(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    if not rechnung.ist_entwurf:
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id))
    return render_template(
        "rechnung_vorschau.html",
        r=rechnung,
        fehler=finalisierungsfehler(rechnung, aktuelles_gewerbe()),
        hinweise=pruefhinweise(rechnung, aktuelles_gewerbe()),
        reverse_charge=reverse_charge_vorschlag(rechnung),
        mail_bereit=mail_eingerichtet() and bool(rechnung.kontakt and rechnung.kontakt.email),
    )


@bp.post("/<int:rechnung_id>/reverse-charge")
@braucht_recht(Recht.ENTWUERFE)
def reverse_charge(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    if rechnung.ist_entwurf:
        ergaenze_reverse_charge(rechnung, current_user.id)
        flash("Hinweis „Steuerschuldnerschaft des Leistungsempfängers“ ergänzt.")
    return redirect(url_for("rechnungen.vorschau", rechnung_id=rechnung.id))


@bp.post("/<int:rechnung_id>/finalisieren")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def finalisieren(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    try:
        finalisiere(rechnung, current_user.id)
    except NichtFinalisierbar:
        db.session.rollback()
        flash("Die Rechnung ist noch nicht vollständig.")
        return redirect(url_for("rechnungen.vorschau", rechnung_id=rechnung.id))
    except NichtBearbeitbar:
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id))
    flash(f"{rechnung.belegname} {rechnung.nummer} ist finalisiert.")
    if request.form.get("danach") == "senden":
        return redirect(url_for("rechnungen.senden", rechnung_id=rechnung.id))
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id))


@bp.get("/<int:rechnung_id>/pdf")
@braucht_recht(Recht.ANSEHEN)
def pdf_anzeigen(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    try:
        inhalt = pdf(rechnung)
    except AblageBeschaedigt:
        abort(
            500, "Die abgelegte PDF-Datei wurde verändert. Bitte aus dem Backup wiederherstellen."
        )
    name = f"{rechnung.titel}-{rechnung.anzeige_nummer}.pdf".replace(" ", "-")
    art = "attachment" if request.args.get("herunterladen") == "1" else "inline"
    return Response(
        inhalt,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'{art}; filename="{name}"'},
    )


@bp.get("/<int:rechnung_id>/xml")
@braucht_recht(Recht.ANSEHEN)
def xml_herunterladen(rechnung_id: int):
    """Die E-Rechnung (CII-XML) einer finalisierten Rechnung, so wie sie festgeschrieben wurde."""
    rechnung = _rechnung(rechnung_id)
    if not rechnung.xml_sha256:
        abort(404)
    name = f"{rechnung.nummer}.xml".replace("/", "_")
    return Response(
        ablage.lies(rechnung.xml_sha256),
        mimetype="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@bp.post("/<int:rechnung_id>/loeschen")
@braucht_recht(Recht.ENTWUERFE)
def loeschen(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    try:
        loesche_entwurf(rechnung, current_user.id)
    except NichtBearbeitbar:
        abort(409)
    flash("Entwurf gelöscht.")
    if rechnung.belegart == "angebot":
        return redirect(url_for("angebote.angebote"))
    return redirect(url_for("rechnungen.liste"))


def _mahnangaben() -> dict:
    """Text und Pauschale aus dem Formular. Ohne Textfeld gelten die Vorschläge."""
    if "text" not in request.form:
        return {"text": None, "pauschale": None}
    return {"text": request.form["text"], "pauschale": request.form.get("pauschale") == "y"}


def _mahnseite(rechnung: Rechnung, fehler: str | None = None):
    stufe = pruefe_mahnbar(rechnung)
    gesendet = request.method == "POST"
    return render_template(
        "mahnung_neu.html",
        r=rechnung,
        stufe=stufe,
        fehler=fehler,
        ab=naechste_faellig_ab(rechnung),
        heute=date.today(),
        text=request.form.get("text", "") if gesendet else stufentext(stufe.nummer),
        pauschale=request.form.get("pauschale") == "y"
        if gesendet
        else pauschale_vorschlag(rechnung, stufe.nummer),
        pauschale_moeglich=stufe.nummer >= PAUSCHALE_AB_STUFE,
        pauschale_cent=VERZUGSPAUSCHALE_CENT,
        stufentexte=[(s, stufentext(s.nummer)) for s in mahnstufen()],
        eigene=mahnvorlagen(),
        platzhalter=PLATZHALTER,
        text_max=TEXT_MAX,
        ohne_bank=not (aktuelles_gewerbe().iban or "").strip(),
    ), (422 if fehler else 200)


@bp.get("/<int:rechnung_id>/mahnungen/neu")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def mahnung_neu(rechnung_id: int):
    try:
        return _mahnseite(_rechnung(rechnung_id))
    except MahnungNichtMoeglich as fehler:
        flash(str(fehler))
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id) + "#mahnungen")


@bp.post("/<int:rechnung_id>/mahnungen/vorschau")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def mahnung_vorschau(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    try:
        mahnung, text = entwurf(rechnung, **_mahnangaben())
    except MahnungNichtMoeglich as fehler:
        flash(str(fehler))
        return redirect(url_for("rechnungen.mahnung_neu", rechnung_id=rechnung_id))
    return Response(
        rendere_mahnung(rechnung, mahnung, text, vorschau_entwurf=True),
        mimetype="application/pdf",
        headers={"Content-Disposition": 'inline; filename="Mahnung-Vorschau.pdf"'},
    )


@bp.post("/<int:rechnung_id>/mahnungen")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def mahnung_erstellen(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    angaben = _mahnangaben()
    vorlagenname = (request.form.get("vorlage_name") or "").strip()
    try:
        pruefe_mahnbar(rechnung)
        if vorlagenname:
            speichere_vorlage(vorlagenname, angaben["text"], current_user.id)
        stufe = request.form.get("stufe", "")
        mahnung = erstelle_mahnung(
            rechnung,
            current_user.id,
            erwartete_stufe=int(stufe) if stufe.isdigit() else None,
            **angaben,
        )
    except MahnungSchonErstellt as fehler:
        db.session.rollback()
        flash(str(fehler))
    except MahnungNichtMoeglich as fehler:
        db.session.rollback()
        if angaben["text"] is not None:
            try:
                return _mahnseite(rechnung, str(fehler))
            except MahnungNichtMoeglich:
                pass
        flash(str(fehler))
    else:
        flash(f"{mahnung.bezeichnung} erstellt. Bitte PDF herunterladen und verschicken.")
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id) + "#mahnungen")


@bp.get("/<int:rechnung_id>/mahnungen/<int:mahnung_id>")
@braucht_recht(Recht.ANSEHEN)
def mahnung_detail(rechnung_id: int, mahnung_id: int):
    mahnung = db.session.get(Mahnung, mahnung_id)
    if not mahnung or mahnung.rechnung_id != rechnung_id:
        abort(404)
    return render_template(
        "mahnung.html",
        m=mahnung,
        r=mahnung.rechnung,
        kette=belegkette(mahnung),
        neueste=ist_neueste(mahnung),
        loeschbar=loeschbar(mahnung),
        verschickt=ist_verschickt(mahnung),
    )


def _mahnung_von(rechnung_id: int, mahnung_id: int) -> Mahnung:
    mahnung = db.session.get(Mahnung, mahnung_id)
    if not mahnung or mahnung.rechnung_id != rechnung_id:
        abort(404)
    return mahnung


@bp.post("/<int:rechnung_id>/mahnungen/<int:mahnung_id>/loeschen")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def mahnung_loeschen(rechnung_id: int, mahnung_id: int):
    mahnung = _mahnung_von(rechnung_id, mahnung_id)
    bezeichnung = mahnung.bezeichnung
    try:
        loesche_mahnung(mahnung, current_user.id)
    except MahnungNichtMoeglich as fehler:
        db.session.rollback()
        flash(str(fehler))
        return redirect(
            url_for("rechnungen.mahnung_detail", rechnung_id=rechnung_id, mahnung_id=mahnung_id)
        )
    flash(f"{bezeichnung} gelöscht.")
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id) + "#mahnungen")


@bp.post("/<int:rechnung_id>/mahnungen/<int:mahnung_id>/zurueckziehen")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def mahnung_zurueckziehen(rechnung_id: int, mahnung_id: int):
    mahnung = _mahnung_von(rechnung_id, mahnung_id)
    try:
        ziehe_zurueck(mahnung, request.form.get("grund"), current_user.id)
    except MahnungNichtMoeglich as fehler:
        db.session.rollback()
        flash(str(fehler))
    else:
        flash(f"{mahnung.bezeichnung} zurückgezogen. Sie zählt nicht mehr als Mahnstufe.")
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id) + "#mahnungen")


@bp.post("/<int:rechnung_id>/lieferschein")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def lieferschein_erstellen(rechnung_id: int):
    try:
        lieferschein = lieferschein_aus_rechnung(_rechnung(rechnung_id), current_user.id)
    except (AktionNichtMoeglich, NichtFinalisierbar) as fehler:
        db.session.rollback()
        flash(
            str(fehler)
            if isinstance(fehler, AktionNichtMoeglich)
            else "Lieferschein nicht möglich."
        )
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id))
    flash(f"Lieferschein {lieferschein.nummer} erstellt.")
    return redirect(url_for("rechnungen.detail", rechnung_id=lieferschein.id))


@bp.get("/<int:rechnung_id>/mahnungen/<int:mahnung_id>/pdf")
@braucht_recht(Recht.ANSEHEN)
def mahnung_pdf(rechnung_id: int, mahnung_id: int):
    mahnung = db.session.get(Mahnung, mahnung_id)
    if not mahnung or mahnung.rechnung_id != rechnung_id:
        abort(404)
    try:
        inhalt = ablage.lies(mahnung.pdf_sha256)
    except AblageBeschaedigt:
        abort(
            500, "Die abgelegte PDF-Datei wurde verändert. Bitte aus dem Backup wiederherstellen."
        )
    name = f"{mahnung.bezeichnung}-{mahnung.rechnung.nummer}.pdf".replace(" ", "-")
    return Response(
        inhalt,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


@bp.post("/<int:rechnung_id>/mahnsperre")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def mahnsperre(rechnung_id: int):
    rechnung = _rechnung(rechnung_id)
    sperre = request.form.get("sperre") == "y"
    setze_mahnsperre(rechnung, sperre, request.form.get("grund"), current_user.id)
    flash("Mahnsperre gesetzt." if sperre else "Mahnsperre aufgehoben.")
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id) + "#mahnungen")


@bp.post("/<int:rechnung_id>/annehmen")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def annehmen(rechnung_id: int):
    return _entscheiden(rechnung_id, True)


@bp.post("/<int:rechnung_id>/offen")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def wieder_offen(rechnung_id: int):
    try:
        oeffne_angebot(_rechnung(rechnung_id), current_user.id)
    except AktionNichtMoeglich as fehler:
        flash(str(fehler))
    else:
        flash("Das Angebot ist wieder offen.")
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id))


@bp.post("/<int:rechnung_id>/ablehnen")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def ablehnen(rechnung_id: int):
    return _entscheiden(rechnung_id, False)


def _entscheiden(rechnung_id: int, angenommen: bool):
    try:
        entscheide_angebot(_rechnung(rechnung_id), angenommen, current_user.id)
    except AktionNichtMoeglich as fehler:
        flash(str(fehler))
    else:
        flash(
            "Angebot als angenommen markiert." if angenommen else "Angebot als abgelehnt markiert."
        )
    return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id))


@bp.post("/<int:rechnung_id>/in-rechnung")
@braucht_recht(Recht.ENTWUERFE)
def in_rechnung(rechnung_id: int):
    try:
        rechnung = rechnung_aus_angebot(_rechnung(rechnung_id), current_user.id)
    except AktionNichtMoeglich as fehler:
        flash(str(fehler))
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id))
    flash("Rechnungsentwurf aus dem Angebot erstellt.")
    return redirect(url_for("rechnungen.bearbeiten", rechnung_id=rechnung.id))


@bp.post("/<int:rechnung_id>/stornieren")
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def stornieren(rechnung_id: int):
    try:
        korrektur = storniere_rechnung(_rechnung(rechnung_id), current_user.id)
    except (AktionNichtMoeglich, NichtFinalisierbar) as fehler:
        db.session.rollback()
        flash(str(fehler))
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung_id))
    flash(f"Rechnung storniert. Rechnungskorrektur {korrektur.nummer} erstellt.")
    return redirect(url_for("rechnungen.detail", rechnung_id=korrektur.id))


def _senden(rechnung: Rechnung, mahnung: Mahnung | None):
    if not (mahnung.pdf_sha256 if mahnung else rechnung.pdf_sha256):
        abort(404)
    if not mail_eingerichtet():
        flash("Bitte zuerst den E-Mail-Versand einrichten (Einstellungen → E-Mail).")
        return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id))
    formular = SendenFormular(
        data=None if request.method == "POST" else vorschlag(rechnung, mahnung)
    )
    if formular.validate_on_submit():
        try:
            versand = sende_beleg(
                rechnung,
                mahnung=mahnung,
                an=formular.an.data,
                betreff=formular.betreff.data,
                text=formular.text.data,
                kopie_an=current_user.email if formular.kopie_an_mich.data else None,
                nutzer_id=current_user.id,
            )
        except MailFehler as fehler:
            formular.an.errors = [*formular.an.errors, str(fehler)]
        else:
            flash(f"E-Mail an {versand.an} verschickt.")
            return redirect(url_for("rechnungen.detail", rechnung_id=rechnung.id) + "#versand")
    return render_template(
        "senden.html",
        formular=formular,
        r=rechnung,
        mahnung=mahnung,
        anhang=dateiname(rechnung, mahnung),
    ), (422 if formular.errors else 200)


@bp.route("/<int:rechnung_id>/senden", methods=["GET", "POST"])
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def senden(rechnung_id: int):
    return _senden(_rechnung(rechnung_id), None)


@bp.route("/<int:rechnung_id>/mahnungen/<int:mahnung_id>/senden", methods=["GET", "POST"])
@braucht_recht(Recht.RECHNUNGEN_VERSENDEN)
def mahnung_senden(rechnung_id: int, mahnung_id: int):
    mahnung = _mahnung_von(rechnung_id, mahnung_id)
    if mahnung.rechnung.status == "storniert":
        flash("Die Rechnung ist storniert, die Mahnung gilt nicht mehr und wird nicht verschickt.")
        return redirect(
            url_for("rechnungen.mahnung_detail", rechnung_id=rechnung_id, mahnung_id=mahnung_id)
        )
    if not mahnung.aktiv:
        flash("Diese Mahnung ist zurückgezogen und kann nicht mehr verschickt werden.")
        return redirect(
            url_for("rechnungen.mahnung_detail", rechnung_id=rechnung_id, mahnung_id=mahnung_id)
        )
    return _senden(mahnung.rechnung, mahnung)
