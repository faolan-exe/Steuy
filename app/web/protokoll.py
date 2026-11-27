"""Änderungsprotokoll ansehen (GoBD: nachvollziehbar, wer wann was getan hat). Nur lesen."""

from flask import Blueprint, render_template, request, url_for
from sqlalchemy import func, select

from app.domain.geld import cent_zu_euro
from app.domain.rollen import Recht
from app.extensions import db
from app.models import Nutzer, Protokoll
from app.web.rechte import braucht_recht

bp = Blueprint("protokoll", __name__, url_prefix="/protokoll")

JE_SEITE = 100

# Wohin ein Eintrag verlinkt (Objekttyp → Endpunkt, Name des Parameters)
ZIELE = {
    "rechnung": ("rechnungen.detail", "rechnung_id"),
    "kontakt": ("kontakte.detail", "kontakt_id"),
    "buchung": ("belege.buchung", "buchung_id"),
    "beleg": ("belege.beleg", "beleg_id"),
}
# Nicht anzeigen: personenbezogen und für die Nachvollziehbarkeit nicht nötig
VERBORGEN = {"ip", "passwort", "token", "schluessel"}


def aktion_text(aktion: str) -> str:
    """„rechnung_finalisiert“ → „Rechnung finalisiert“."""
    text = aktion.replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def ziel(eintrag: Protokoll) -> str | None:
    if eintrag.objekt_typ in ZIELE and (eintrag.objekt_id or "").isdigit():
        endpunkt, parameter = ZIELE[eintrag.objekt_typ]
        return url_for(endpunkt, **{parameter: int(eintrag.objekt_id)})
    return None


def details_text(details: dict | None) -> str:
    if not details:
        return ""
    teile = []
    for schluessel, wert in details.items():
        if schluessel in VERBORGEN or "sha256" in schluessel or wert in (None, "", [], {}):
            continue
        if isinstance(wert, bool):
            wert = "ja" if wert else "nein"
        elif schluessel.endswith("_cent") and isinstance(wert, int):
            schluessel, wert = schluessel.removesuffix("_cent"), cent_zu_euro(wert)
        elif isinstance(wert, dict | list):
            wert = ", ".join(str(w) for w in (wert.values() if isinstance(wert, dict) else wert))
        teile.append(f"{schluessel.replace('_', ' ')}: {str(wert)[:80]}")
    return " · ".join(teile)


@bp.get("")
@braucht_recht(Recht.PROTOKOLL)
def liste():
    seite = max(1, request.args.get("seite", 1, type=int))
    abfrage = select(Protokoll)
    objekt_typ = request.args.get("objekt") or None
    objekt_id = request.args.get("id") or None
    if objekt_typ:
        abfrage = abfrage.where(Protokoll.objekt_typ == objekt_typ)
        if objekt_id:
            abfrage = abfrage.where(Protokoll.objekt_id == objekt_id)
    anzahl = db.session.execute(select(func.count()).select_from(abfrage.subquery())).scalar()
    eintraege = list(
        db.session.execute(
            abfrage.order_by(Protokoll.id.desc()).offset((seite - 1) * JE_SEITE).limit(JE_SEITE)
        ).scalars()
    )
    nutzer = {n.id: n for n in db.session.execute(select(Nutzer)).scalars()}
    return render_template(
        "protokoll.html",
        eintraege=eintraege,
        nutzer=nutzer,
        seite=seite,
        weitere=anzahl > seite * JE_SEITE,
        anzahl=anzahl,
        objekt_typ=objekt_typ,
        objekt_id=objekt_id,
        aktion_text=aktion_text,
        ziel=ziel,
        details_text=details_text,
    )
