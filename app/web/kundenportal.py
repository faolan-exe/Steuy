"""Öffentliche Seiten des Kundenportals unter /k/<schlüssel>.

Ausnahme von Regel 3 („jede Route prüft Rechte“): Hier gibt es keine Anmeldung, der
Schlüssel im Link ist die Berechtigung und reicht genau für einen Beleg (docs/kundenportal.md).
"""

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.domain.iban import formatiere_iban
from app.models import Mahnung
from app.services import ablage
from app.services import kundenportal as portal
from app.services.einrichtung import aktuelles_gewerbe

bp = Blueprint("kunde", __name__, url_prefix="/k")

SITZUNG = "kundenlinks"  # IDs der Links, deren PLZ in dieser Sitzung bestätigt wurde


def _link(schluessel: str, mit_plz: bool = True):
    link = portal.finde(schluessel)
    if not link:
        abort(404)
    if mit_plz and portal.plz_noetig(link) and link.id not in session.get(SITZUNG, []):
        return link, False
    return link, True


def _seite(vorlage: str, status: int = 200, **werte):
    antwort = Response(render_template(vorlage, **werte), status=status)
    _kopfzeilen(antwort)
    return antwort


def _kopfzeilen(antwort: Response) -> Response:
    # Der Schlüssel steht in der Adresse: nie als Referrer weitergeben, nie indexieren
    antwort.headers["Referrer-Policy"] = "no-referrer"
    antwort.headers["X-Robots-Tag"] = "noindex, nofollow"
    return antwort


@bp.errorhandler(404)
def nicht_gefunden(_fehler):
    from app.services.drucklayout import logo_daten_uri

    return _seite("kunde/ungueltig.html", 404, gewerbe=aktuelles_gewerbe(), logo=logo_daten_uri())


@bp.route("/<schluessel>", methods=["GET", "POST"])
def beleg(schluessel: str):
    link, frei = _link(schluessel)
    if not frei:
        fehler = None
        if request.method == "POST":
            try:
                richtig = portal.pruefe_plz(link, request.form.get("plz", ""))
            except portal.PortalFehler as f:
                fehler, richtig = str(f), False
            if richtig:
                session[SITZUNG] = [*session.get(SITZUNG, [])[-20:], link.id]
                return redirect(url_for("kunde.beleg", schluessel=schluessel))
            fehler = fehler or "Die Postleitzahl stimmt nicht."
        from app.services.drucklayout import logo_daten_uri

        return _seite(
            "kunde/plz.html",
            401 if fehler else 200,
            link=link,
            fehler=fehler,
            gewerbe=aktuelles_gewerbe(),
            logo=logo_daten_uri(),
        )

    if request.method == "GET":
        portal.merke_abruf(link)
    r = link.rechnung
    absender = r.absender or {}
    from app.services.drucklayout import logo_daten_uri
    from app.services.pdf import _qr_fuer

    offen = r.offen_cent if r.belegart == "rechnung" and r.status != "storniert" else 0
    return _seite(
        "kunde/beleg.html",
        link=link,
        r=r,
        schluessel=schluessel,
        zustand=portal.status(r),
        absender=absender,
        iban=formatiere_iban(absender["iban"]) if absender.get("iban") else None,
        offen=offen,
        qr=_qr_fuer(absender, offen, r.nummer) if offen > 0 and r.qr_ueberweisung else None,
        mahnungen=portal.mahnungen(r),
        kann_entscheiden=portal.kann_entscheiden(r),
        logo=logo_daten_uri(),
        gewerbe=aktuelles_gewerbe(),
    )


def _datei(inhalt: bytes, name: str, mime: str, herunterladen: bool) -> Response:
    art = "attachment" if herunterladen else "inline"
    antwort = Response(
        inhalt,
        mimetype=mime,
        headers={
            "Content-Disposition": f'{art}; filename="{name}"',
            "Content-Security-Policy": "default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )
    return _kopfzeilen(antwort)


def _dateiname(text: str) -> str:
    return "".join(z if z.isalnum() or z in "-_." else "-" for z in text)


@bp.get("/<schluessel>/pdf")
def pdf(schluessel: str):
    link, frei = _link(schluessel)
    if not frei:
        return redirect(url_for("kunde.beleg", schluessel=schluessel))
    r = link.rechnung
    return _datei(
        ablage.lies(r.pdf_sha256),
        _dateiname(f"{r.titel}-{r.nummer}.pdf"),
        "application/pdf",
        request.args.get("herunterladen") == "1",
    )


@bp.get("/<schluessel>/xml")
def xml(schluessel: str):
    link, frei = _link(schluessel)
    if not frei:
        return redirect(url_for("kunde.beleg", schluessel=schluessel))
    r = link.rechnung
    if not r.xml_sha256:
        abort(404)
    return _datei(ablage.lies(r.xml_sha256), _dateiname(f"{r.nummer}.xml"), "application/xml", True)


@bp.get("/<schluessel>/mahnung/<int:mahnung_id>")
def mahnung(schluessel: str, mahnung_id: int):
    link, frei = _link(schluessel)
    if not frei:
        return redirect(url_for("kunde.beleg", schluessel=schluessel))
    m = next((x for x in portal.mahnungen(link.rechnung) if x.id == mahnung_id), None)
    if not isinstance(m, Mahnung):
        abort(404)
    return _datei(
        ablage.lies(m.pdf_sha256),
        _dateiname(f"{m.bezeichnung}-{link.rechnung.nummer}.pdf"),
        "application/pdf",
        request.args.get("herunterladen") == "1",
    )


@bp.post("/<schluessel>/entscheiden")
def entscheiden(schluessel: str):
    link, frei = _link(schluessel)
    if not frei:
        return redirect(url_for("kunde.beleg", schluessel=schluessel))
    angenommen = request.form.get("entscheidung") == "annehmen"
    if angenommen and request.form.get("verbindlich") != "ja":
        flash("Bitte bestätigen Sie, dass Sie das Angebot verbindlich annehmen.")
        return redirect(url_for("kunde.beleg", schluessel=schluessel) + "#entscheidung")
    try:
        portal.entscheide(
            link, angenommen, request.form.get("name", ""), request.form.get("kommentar", "")
        )
    except portal.PortalFehler as fehler:
        flash(str(fehler))
        return redirect(url_for("kunde.beleg", schluessel=schluessel) + "#entscheidung")
    flash(
        "Vielen Dank! Das Angebot ist angenommen, wir melden uns."
        if angenommen
        else "Danke für Ihre Rückmeldung. Das Angebot ist abgelehnt."
    )
    return redirect(url_for("kunde.beleg", schluessel=schluessel))
