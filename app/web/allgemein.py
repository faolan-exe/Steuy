from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.domain.geld import GeldFormatFehler, cent_zu_euro, euro_zu_cent
from app.domain.motivation import ZIELARTEN, spruch, ziel_stand
from app.domain.rollen import Recht
from app.extensions import db
from app.services.einrichtung import aktuelles_gewerbe, grenze, setze_ziel
from app.services.suche import MIN_ZEICHEN, suche
from app.services.zahlungen import jahre_mit_daten, kennzahlen, rechnungsstand, zu_pruefen
from app.web.rechte import braucht_recht

bp = Blueprint("allgemein", __name__)


def _diagrammpunkte(
    werte: list[int], hoechster: int, breite=660, hoehe=200, links=50, oben=20
) -> str:
    """SVG-Polyline für zwölf Monatswerte, skaliert auf den gemeinsamen Höchstwert."""
    schritt = breite / 11
    return " ".join(
        f"{links + i * schritt:.1f},{oben + hoehe - wert / hoechster * hoehe:.1f}"
        for i, wert in enumerate(werte)
    )


@bp.get("/")
@braucht_recht(Recht.ANSEHEN)
def start():
    aktuell = date.today().year
    gewaehlt = request.args.get("jahr", "")
    # Nur Jahre, für die es Daten gibt
    jahre = jahre_mit_daten()
    jahr = int(gewaehlt) if gewaehlt.isdigit() and int(gewaehlt) in jahre else aktuell
    werte = kennzahlen(jahr)
    uebersicht = {
        "jahr": jahr,
        "einnahmen_cent": werte["einnahmen_cent"],
        "ausgaben_cent": werte["ausgaben_cent"],
        "umsatz_cent": werte["einnahmen_cent"],
        "offen_cent": werte["offen_cent"],
        "offen_ausgaben_cent": 0,
        "zaehler": [
            (werte["anzahl_rechnungen"], "Rechnungen"),
            (werte["anzahl_angebote"], "Angebote"),
        ],
        "linien": None,
    }
    if werte["einnahmen_cent"] or werte["ausgaben_cent"]:
        hoechster = max(*werte["einnahmen_monate"], *werte["ausgaben_monate"], 1)
        uebersicht["linien"] = {
            "einnahmen": _diagrammpunkte(werte["einnahmen_monate"], hoechster),
            "ausgaben": _diagrammpunkte(werte["ausgaben_monate"], hoechster),
        }
    stand = rechnungsstand(jahr)
    gewerbe = aktuelles_gewerbe()
    ziel = None
    if gewerbe and gewerbe.ziel_art and gewerbe.ziel_wert:
        aktuell = {
            "auftraege": stand["bezahlt"],
            "umsatz": werte["einnahmen_cent"],
            "gewinn": werte["einnahmen_cent"] - werte["ausgaben_cent"],
        }[gewerbe.ziel_art]
        ziel = ziel_stand(gewerbe.ziel_art, gewerbe.ziel_wert, aktuell)
        ziel["eingabe"] = (
            str(gewerbe.ziel_wert)
            if gewerbe.ziel_art == "auftraege"
            else cent_zu_euro(gewerbe.ziel_wert)[:-2]
        )
    return render_template(
        "start.html",
        stand=stand,
        ziel=ziel,
        zielarten=ZIELARTEN,
        motivation=spruch(
            gesamt=stand["gesamt_alle"],
            bezahlt=stand["bezahlt"],
            offen=stand["offen"],
            ueberfaellig=stand["ueberfaellig"],
            einnahmen_cent=werte["einnahmen_cent"],
            jahr=jahr,
            heute=date.today(),
        ),
        uebersicht=uebersicht,
        grenze=grenze(jahr),
        offen=zu_pruefen(),
        jahre=jahre,
        aktuell_jahr=aktuell,
    )


@bp.post("/ziel")
@braucht_recht(Recht.EINSTELLUNGEN)
def ziel_setzen():
    art = request.form.get("art", "")
    if request.form.get("aktion") == "entfernen" or art == "":
        setze_ziel(None, None, current_user.id)
        flash("Ziel entfernt.")
        return redirect(url_for("allgemein.start"))
    text = request.form.get("wert", "").strip()
    try:
        if art not in ZIELARTEN:
            raise ValueError
        wert = int(text) if art == "auftraege" else euro_zu_cent(text)
        if not 0 < wert <= 10**12:
            raise ValueError
    except (ValueError, GeldFormatFehler):
        flash("Bitte Zielart wählen und einen Wert über 0 eingeben, z. B. 25 oder 20.000,00.")
        return redirect(url_for("allgemein.start", ziel_aendern=1))
    setze_ziel(art, wert, current_user.id)
    flash("Ziel gespeichert.")
    return redirect(url_for("allgemein.start"))


@bp.get("/zu-pruefen")
@braucht_recht(Recht.ANSEHEN)
def pruefen():
    from app.services.shop import eingerichtet as shop_eingerichtet

    gewerbe = aktuelles_gewerbe()
    return render_template(
        "zu_pruefen.html",
        offen=zu_pruefen(),
        heute=date.today(),
        shop_verbunden=shop_eingerichtet(),
        g_shop_abruf=gewerbe.shop_letzter_abruf if gewerbe else None,
    )


@bp.get("/suche")
@braucht_recht(Recht.ANSEHEN)
def suche_seite():
    anfrage = request.args.get("q", "").strip()
    ergebnis = suche(anfrage)
    return render_template(
        "suche.html",
        q=anfrage,
        ergebnis=ergebnis,
        anzahl=sum(len(v) for v in ergebnis.values()),
        zu_kurz=0 < len(anfrage) < MIN_ZEICHEN,
    )


@bp.get("/gesund")
def gesund():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return jsonify(status="fehler", datenbank="nicht erreichbar"), 503
    return jsonify(status="ok", datenbank="ok")
