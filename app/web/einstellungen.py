from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from app.domain.drucklayout import (
    FARBVORSCHLAEGE,
    LAYOUTS,
    LOGO_POSITIONEN,
    LOGO_PROZENT,
    SCHRIFTEN,
    TEXT_PT,
    TITEL_PT,
    LayoutUngueltig,
    pruefe,
)
from app.domain.passwort import PasswortZuKurz
from app.domain.rollen import (
    EINSTELLBAR,
    EINSTELLBARE_ROLLEN,
    NUR_ADMIN,
    RECHTE_NAMEN,
    ROLLEN_NAMEN,
    Recht,
    Rolle,
)
from app.extensions import db
from app.models import Mahnstufe, Nutzer
from app.services import drucklayout as layoutdienst
from app.services import scaneingang
from app.services.drucklayout_vorschau import vorschau_html
from app.services.einrichtung import aktuelles_gewerbe
from app.services.firmendaten import aendere_firmendaten
from app.services.mahnwesen import aendere_stufen, setze_automatik
from app.services.mail import MailFehler, eingerichtet, sende
from app.services.nutzerverwaltung import (
    EmailVergeben,
    LetzterAdmin,
    aendere_nutzer,
    alle_nutzer,
    lege_nutzer_an,
)
from app.services.protokoll import protokolliere
from app.services.rechnungseinstellungen import (
    NummerSchonVergeben,
    aendere_mail_einstellungen,
    aendere_rechnungseinstellungen,
    rechnungskreis,
)
from app.services.rechte import rechte_matrix, setze_rechte
from app.services.update import automatisch_moeglich as update_moeglich
from app.services.update import pruefe as pruefe_update
from app.services.update import starte_update, ueberspringe, vergiss_ueberspringen
from app.services.update import status as update_status
from app.services.zwei_faktor import deaktiviere
from app.version import VERSION
from app.web.formulare import (
    FirmendatenFormular,
    MailEinstellungenFormular,
    NutzerAnlegenFormular,
    NutzerBearbeitenFormular,
    RechnungseinstellungenFormular,
)
from app.web.rechte import braucht_recht

bp = Blueprint("einstellungen", __name__, url_prefix="/einstellungen")


@bp.route("/firma", methods=["GET", "POST"])
@braucht_recht(Recht.EINSTELLUNGEN)
def firmendaten():
    gewerbe = aktuelles_gewerbe()
    formular = FirmendatenFormular(obj=gewerbe)
    if formular.validate_on_submit():
        if aendere_firmendaten(gewerbe, formular.data, current_user.id):
            flash("Firmendaten gespeichert.")
        else:
            flash("Keine Änderungen.")
        return redirect(url_for("einstellungen.firmendaten"))

    return render_template("firmendaten.html", formular=formular)


@bp.get("/import-export")
@braucht_recht(Recht.EINSTELLUNGEN)
def import_export():
    return render_template("import_export.html")


@bp.route("/drucklayout", methods=["GET", "POST"])
@braucht_recht(Recht.EINSTELLUNGEN)
def drucklayout():
    layout = layoutdienst.aktuell()
    if request.method == "POST":
        try:
            layout = pruefe(request.form)
        except LayoutUngueltig as fehler:
            flash(str(fehler))
        else:
            layoutdienst.speichere(layout, current_user.id)
            flash("Drucklayout gespeichert. Neue Belege sehen jetzt so aus.")
            return redirect(url_for("einstellungen.drucklayout"))
    return render_template(
        "drucklayout.html",
        d=layout,
        layouts=LAYOUTS,
        schriften=SCHRIFTEN,
        farben=FARBVORSCHLAEGE,
        logo_positionen=LOGO_POSITIONEN,
        logo=layoutdienst.logo_daten_uri(),
        grenzen={"logo": LOGO_PROZENT, "text": TEXT_PT, "titel": TITEL_PT},
    )


@bp.get("/drucklayout/vorschau")
@braucht_recht(Recht.EINSTELLUNGEN)
def drucklayout_vorschau():
    """Beispielrechnung mit den Werten aus der Adresse (ungespeichert) für den Editor."""
    werte = {name: request.args.get(name) for name in request.args}
    try:
        # Ohne Angaben (erster Aufruf) gilt das gespeicherte Layout
        layout = pruefe(werte) if werte else layoutdienst.aktuell()
    except LayoutUngueltig:
        layout = layoutdienst.aktuell()
    return Response(vorschau_html(layout), mimetype="text/html")


@bp.post("/drucklayout/logo")
@braucht_recht(Recht.EINSTELLUNGEN)
def drucklayout_logo():
    datei = request.files.get("logo")
    try:
        layoutdienst.setze_logo(datei.read() if datei else b"", current_user.id)
    except layoutdienst.LogoUngueltig as fehler:
        flash(str(fehler))
    else:
        flash("Logo gespeichert.")
    return redirect(url_for("einstellungen.drucklayout"))


@bp.post("/drucklayout/logo/entfernen")
@braucht_recht(Recht.EINSTELLUNGEN)
def drucklayout_logo_entfernen():
    layoutdienst.entferne_logo(current_user.id)
    flash("Logo entfernt.")
    return redirect(url_for("einstellungen.drucklayout"))


@bp.post("/drucklayout/zuruecksetzen")
@braucht_recht(Recht.EINSTELLUNGEN)
def drucklayout_zuruecksetzen():
    layoutdienst.zuruecksetzen(current_user.id)
    flash("Drucklayout auf die Standardwerte zurückgesetzt.")
    return redirect(url_for("einstellungen.drucklayout"))


@bp.get("/update")
@braucht_recht(Recht.EINSTELLUNGEN)
def update():
    frisch = request.args.get("pruefen") == "1"
    return render_template(
        "update.html",
        ergebnis=pruefe_update(frisch=frisch),
        status=update_status(),
        automatisch=update_moeglich(),
        version=VERSION,
    )


@bp.get("/update/status")
@braucht_recht(Recht.EINSTELLUNGEN)
def update_fortschritt():
    return jsonify({**update_status(), "installiert": VERSION})


@bp.post("/update/starten")
@braucht_recht(Recht.EINSTELLUNGEN)
def update_starten():
    ergebnis = pruefe_update()
    if ergebnis.zustand not in ("neu", "uebersprungen") or not ergebnis.neueste:
        flash("Es gibt kein Update zum Installieren.")
        return redirect(url_for("einstellungen.update"))
    try:
        starte_update(ergebnis.neueste, current_user.id)
    except RuntimeError as fehler:
        flash(str(fehler))
    else:
        flash(f"Update auf {ergebnis.neueste} gestartet. Vorher wird eine Sicherung angelegt.")
    return redirect(url_for("einstellungen.update"))


@bp.post("/update/ueberspringen")
@braucht_recht(Recht.EINSTELLUNGEN)
def update_ueberspringen():
    ergebnis = pruefe_update()
    if request.form.get("aktion") == "doch" or ergebnis.zustand == "uebersprungen":
        vergiss_ueberspringen(current_user.id)
        flash("Das Update wird wieder angeboten.")
    elif ergebnis.zustand == "neu" and ergebnis.neueste:
        ueberspringe(ergebnis.neueste, current_user.id)
        flash(f"Version {ergebnis.neueste} übersprungen. Erst eine neuere wird wieder angeboten.")
    return redirect(url_for("einstellungen.update"))


@bp.route("/nutzer", methods=["GET", "POST"])
@braucht_recht(Recht.NUTZER_VERWALTEN)
def nutzer():
    formular = NutzerAnlegenFormular()
    if formular.validate_on_submit():
        try:
            neu = lege_nutzer_an(
                formular.name.data,
                formular.email.data,
                formular.rolle.data,
                formular.passwort.data,
                formular.zugang_bis.data,
                current_user.id,
            )
        except EmailVergeben as fehler:
            formular.email.errors.append(str(fehler))
        else:
            flash(f"{neu.name} wurde angelegt.")
            return redirect(url_for("einstellungen.nutzer"))

    return render_template(
        "nutzer.html", formular=formular, nutzerliste=alle_nutzer(), rollen=ROLLEN_NAMEN
    )


@bp.route("/nutzer/<int:nutzer_id>", methods=["GET", "POST"])
@braucht_recht(Recht.NUTZER_VERWALTEN)
def nutzer_bearbeiten(nutzer_id: int):
    person = db.session.get(Nutzer, nutzer_id) or abort(404)
    formular = NutzerBearbeitenFormular(obj=person)
    fehler = None
    if formular.validate_on_submit():
        try:
            aenderungen = aendere_nutzer(
                person,
                admin_id=current_user.id,
                name=formular.name.data,
                email=formular.email.data,
                rolle=formular.rolle.data,
                aktiv=formular.aktiv.data,
                zugang_bis=formular.zugang_bis.data,
                neues_passwort=formular.neues_passwort.data or None,
            )
        except EmailVergeben as e:
            formular.email.errors.append(str(e))
        except (LetzterAdmin, PasswortZuKurz) as e:
            db.session.rollback()
            fehler = str(e)
        else:
            flash("Gespeichert." if aenderungen else "Keine Änderungen.")
            return redirect(url_for("einstellungen.nutzer"))

    return render_template(
        "nutzer_bearbeiten.html", formular=formular, person=person, fehler=fehler
    )


@bp.route("/rechte", methods=["GET", "POST"])
@braucht_recht(Recht.NUTZER_VERWALTEN)
def rechte():
    if request.method == "POST":
        neu = {
            rolle: {r for r in EINSTELLBAR if request.form.get(f"{rolle.value}:{r.value}")}
            for rolle in EINSTELLBARE_ROLLEN
        }
        flash("Rechte gespeichert." if setze_rechte(neu, current_user.id) else "Keine Änderungen.")
        return redirect(url_for("einstellungen.rechte"))

    return render_template(
        "rechte.html",
        matrix=rechte_matrix(),
        rechte=list(Recht),
        rechte_namen=RECHTE_NAMEN,
        einstellbar=set(EINSTELLBAR),
        nur_admin=NUR_ADMIN,
        rollen=EINSTELLBARE_ROLLEN,
        rollen_namen=ROLLEN_NAMEN,
        admin=Rolle.ADMIN,
    )


@bp.route("/rechnungen", methods=["GET", "POST"])
@braucht_recht(Recht.EINSTELLUNGEN)
def rechnungen():
    gewerbe = aktuelles_gewerbe()
    kreis = rechnungskreis()
    formular = RechnungseinstellungenFormular(
        obj=gewerbe,
        praefix=kreis.praefix,
        stellen=kreis.stellen,
        naechste_nummer=kreis.naechste_nummer,
    )
    if formular.validate_on_submit():
        try:
            geaendert = aendere_rechnungseinstellungen(gewerbe, formular.data, current_user.id)
        except NummerSchonVergeben as fehler:
            db.session.rollback()
            formular.naechste_nummer.errors.append(str(fehler))
        else:
            flash("Gespeichert." if geaendert else "Keine Änderungen.")
            return redirect(url_for("einstellungen.rechnungen"))
    return render_template("rechnungseinstellungen.html", formular=formular)


@bp.route("/email", methods=["GET", "POST"])
@braucht_recht(Recht.EINSTELLUNGEN)
def email():
    gewerbe = aktuelles_gewerbe()
    formular = MailEinstellungenFormular(obj=gewerbe)
    if request.method == "GET":
        formular.smtp_passwort.data = ""
    if formular.validate_on_submit():
        daten = {**formular.data, "passwort_loeschen": request.form.get("passwort_loeschen")}
        geaendert = aendere_mail_einstellungen(gewerbe, daten, current_user.id)
        flash("Gespeichert." if geaendert else "Keine Änderungen.")
        return redirect(url_for("einstellungen.email"))
    return render_template(
        "mail_einstellungen.html", formular=formular, eingerichtet=eingerichtet(), g_=gewerbe
    )


@bp.post("/email/test")
@braucht_recht(Recht.EINSTELLUNGEN)
def email_test():
    try:
        sende(
            an=current_user.email,
            betreff="Test-Mail von steuy",
            text=(
                f"Hallo {current_user.name},\n\n"
                "diese Nachricht zeigt: Der E-Mail-Versand von steuy funktioniert.\n"
            ),
        )
    except MailFehler as fehler:
        flash(f"Test fehlgeschlagen: {fehler}")
    else:
        flash(f"Test-Mail an {current_user.email} verschickt. Bitte im Postfach prüfen.")
    return redirect(url_for("einstellungen.email"))


@bp.route("/scanner", methods=["GET", "POST"])
@braucht_recht(Recht.EINSTELLUNGEN)
def scanner():
    if request.method == "POST":
        an = request.form.get("aktiv") == "y"
        try:
            scaneingang.setze_aktiv(
                an,
                current_user.id,
                freigabe=request.form.get("freigabe") == "y",
                kompatibel=request.form.get("kompatibel") == "y",
            )
        except OSError:
            db.session.rollback()
            flash("Der Ordner für den Scan-Eingang konnte nicht angelegt werden.")
        else:
            flash("Scan-Eingang eingeschaltet." if an else "Scan-Eingang ausgeschaltet.")
        return redirect(url_for("einstellungen.scanner"))
    return render_template(
        "scanner.html",
        s=scaneingang.status(),
        g_=aktuelles_gewerbe(),
        aktiv=scaneingang.ist_aktiv(),
        rechner=request.host.rsplit(":", 1)[0] if ":" in request.host else request.host,
    )


@bp.post("/scanner/passwort")
@braucht_recht(Recht.EINSTELLUNGEN)
def scanner_passwort():
    if not scaneingang.ist_aktiv():
        flash("Bitte zuerst den Scan-Eingang einschalten.")
    else:
        scaneingang.erneuere_passwort(current_user.id)
        flash("Neues Passwort erzeugt. Bitte im Scanner eintragen.")
    return redirect(url_for("einstellungen.scanner"))


@bp.post("/scanner/pruefen")
@braucht_recht(Recht.EINSTELLUNGEN)
def scanner_pruefen():
    if not scaneingang.ist_aktiv():
        flash("Bitte zuerst den Scan-Eingang einschalten.")
    else:
        ergebnis = scaneingang.pruefe_ordner(ruhezeit=3)
        flash(ergebnis.text())
        for name, grund in ergebnis.fehler:
            flash(f"{name}: {grund}")
    return redirect(url_for("einstellungen.scanner"))


@bp.post("/mahnwesen/automatik")
@braucht_recht(Recht.EINSTELLUNGEN)
def mahnautomatik():
    an = request.form.get("auto_mahnen") == "y"
    setze_automatik(an, current_user.id)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"auto_mahnen": an})
    flash("Automatisches Mahnen eingeschaltet." if an else "Automatisches Mahnen ausgeschaltet.")
    return redirect(url_for("einstellungen.mahnwesen"))


@bp.route("/mahnwesen", methods=["GET", "POST"])
@braucht_recht(Recht.EINSTELLUNGEN)
def mahnwesen():
    stufen = list(db.session.execute(db.select(Mahnstufe).order_by(Mahnstufe.nummer)).scalars())
    fehler: dict[str, str] = {}
    if request.method == "POST":
        daten = {}
        for stufe in stufen:
            pre = f"stufe-{stufe.nummer}-"
            werte = {
                "bezeichnung": (request.form.get(pre + "bezeichnung") or "").strip()[:60],
                "text": (request.form.get(pre + "text") or "").strip(),
            }
            for feld in ("tage_nach", "frist_tage"):
                roh = (request.form.get(pre + feld) or "").strip()
                if not roh.isdigit() or int(roh) > 365:
                    fehler[pre + feld] = "Bitte Tage zwischen 0 und 365."
                else:
                    werte[feld] = int(roh)
            for feld in ("bezeichnung", "text"):
                if not werte[feld]:
                    fehler[pre + feld] = "Pflichtfeld"
            daten[stufe.nummer] = werte
        if not fehler:
            geaendert = aendere_stufen(daten, current_user.id)
            flash("Gespeichert." if geaendert else "Keine Änderungen.")
            return redirect(url_for("einstellungen.mahnwesen"))
        return render_template(
            "mahnwesen.html", stufen=stufen, fehler=fehler, form=request.form
        ), 422
    return render_template("mahnwesen.html", stufen=stufen, fehler=fehler, form=None)


@bp.post("/zwei-faktor-pflicht")
@braucht_recht(Recht.NUTZER_VERWALTEN)
def zwei_faktor_pflicht():
    gewerbe = aktuelles_gewerbe()
    pflicht = request.form.get("pflicht") == "y"
    if gewerbe.zwei_faktor_pflicht != pflicht:
        gewerbe.zwei_faktor_pflicht = pflicht
        protokolliere(
            "zwei_faktor_pflicht", nutzer_id=current_user.id, details={"pflicht": pflicht}
        )
        db.session.commit()
    flash(
        "Zwei-Faktor-Anmeldung ist jetzt für alle verpflichtend."
        if pflicht
        else "Zwei-Faktor-Anmeldung ist freiwillig."
    )
    return redirect(url_for("einstellungen.nutzer"))


@bp.post("/nutzer/<int:nutzer_id>/zwei-faktor-zuruecksetzen")
@braucht_recht(Recht.NUTZER_VERWALTEN)
def zwei_faktor_zuruecksetzen(nutzer_id: int):
    person = db.session.get(Nutzer, nutzer_id) or abort(404)
    deaktiviere(person, current_user.id)
    flash(f"Zwei-Faktor-Anmeldung von {person.name} zurückgesetzt. Bitte neu einrichten lassen.")
    return redirect(url_for("einstellungen.nutzer_bearbeiten", nutzer_id=nutzer_id))
