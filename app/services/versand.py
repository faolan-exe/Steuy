"""Rechnungen, Angebote und Mahnungen per E-Mail verschicken, mit Verlauf."""

from datetime import date

from app.domain.geld import cent_zu_euro
from app.domain.mail import KNOPF_TEXTE, Anhang, als_html, vorlage
from app.extensions import db
from app.models import Mahnung, Rechnung, Versand
from app.services import ablage
from app.services.einrichtung import aktuelles_gewerbe
from app.services.mail import MailFehler, sende
from app.services.protokoll import protokolliere


def _datum(wert: date | None) -> str:
    return wert.strftime("%d.%m.%Y") if wert else ""


def dateiname(rechnung: Rechnung, mahnung: Mahnung | None = None) -> str:
    if mahnung:
        return f"{mahnung.bezeichnung}-{rechnung.nummer}.pdf".replace(" ", "-")
    return f"{rechnung.titel}-{rechnung.anzeige_nummer}.pdf".replace(" ", "-")


def portal_link(rechnung: Rechnung) -> str | None:
    from app.services import kundenportal

    return kundenportal.url_fuer(rechnung)


def vorschlag(rechnung: Rechnung, mahnung: Mahnung | None = None) -> dict[str, str]:
    """Empfänger, Betreff und Text zum Bearbeiten vor dem Senden."""
    gewerbe = aktuelles_gewerbe()
    werte = {
        "nummer": rechnung.anzeige_nummer,
        "firma": gewerbe.name,
        "inhaber": gewerbe.inhaber,
        "betrag": cent_zu_euro(mahnung.gesamt_cent if mahnung else rechnung.summe_cent),
        "faellig": _datum(rechnung.faellig_am),
        "gueltig": _datum(rechnung.gueltig_bis),
        "bezeichnung": mahnung.bezeichnung if mahnung else "",
        "frist": _datum(mahnung.frist_bis) if mahnung else "",
        "link": portal_link(rechnung) or "",
    }
    art = "mahnung" if mahnung else rechnung.belegart
    if art == "rechnung":
        if rechnung.status == "bezahlt":
            art = "rechnung_bezahlt"
        elif rechnung.status == "teilbezahlt":
            art = "rechnung_teilbezahlt"
            werte["offen"] = cent_zu_euro(rechnung.offen_cent)
        elif not rechnung.qr_ueberweisung:
            art = "rechnung_ohne_qr"
    betreff, text = vorlage(art, werte)
    an = rechnung.kontakt.email if rechnung.kontakt and rechnung.kontakt.email else ""
    return {"an": an, "betreff": betreff, "text": text}


def sende_beleg(
    rechnung: Rechnung,
    *,
    an: str,
    betreff: str,
    text: str,
    nutzer_id: int,
    mahnung: Mahnung | None = None,
    kopie_an: str | None = None,
) -> Versand:
    """Schickt das unveränderte PDF. Auch ein Fehlversuch landet im Verlauf."""
    sha = mahnung.pdf_sha256 if mahnung else rechnung.pdf_sha256
    if not sha:
        raise MailFehler("Nur finalisierte Belege lassen sich verschicken.")
    name = dateiname(rechnung, mahnung)
    versand = Versand(
        rechnung_id=rechnung.id,
        mahnung_id=mahnung.id if mahnung else None,
        an=(an or "").strip()[:254],
        kopie_an=(kopie_an or "").strip()[:254] or None,
        betreff=" ".join((betreff or "").split())[:200],
        text=text or "",
        anhang=name,
        gesendet_von=nutzer_id,
    )
    link = portal_link(rechnung)
    art = "mahnung" if mahnung else rechnung.belegart
    # Steht der Portal-Link (noch) im Text, gibt es ihn in der HTML-Fassung als Knopf
    html = als_html(text, link, KNOPF_TEXTE.get(art, "Ansehen")) if link and link in text else None
    try:
        sende(
            an=an,
            betreff=betreff,
            text=text,
            kopie_an=kopie_an or None,
            anhaenge=(Anhang(name, ablage.lies(sha)),),
            html=html,
        )
    except MailFehler as fehler:
        versand.erfolgreich = False
        versand.fehler = str(fehler)
        if versand.an:
            db.session.add(versand)
            db.session.commit()
        raise
    versand.erfolgreich = True
    db.session.add(versand)
    db.session.flush()
    protokolliere(
        "beleg_versendet",
        nutzer_id=nutzer_id,
        objekt_typ="rechnung",
        objekt_id=rechnung.id,
        details={"versand_id": versand.id, "an": versand.an, "mahnung_id": versand.mahnung_id},
    )
    db.session.commit()
    return versand


def nicht_verschickt(tage: int = 30) -> list[dict]:
    """Was steuy von selbst verschicken wollte und nicht konnte, damit es nicht untergeht:
    gescheiterte Versuche ohne späteren Erfolg und automatische Mahnungen ohne Versand."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.extensions import db

    seit = datetime.now(UTC) - timedelta(days=tage)
    versuche = list(
        db.session.execute(
            select(Versand).where(Versand.gesendet_am >= seit).order_by(Versand.gesendet_am)
        ).scalars()
    )
    erfolgreich = {(v.rechnung_id, v.mahnung_id) for v in versuche if v.erfolgreich}
    offen: dict[tuple, dict] = {}
    for v in versuche:
        schluessel = (v.rechnung_id, v.mahnung_id)
        if v.erfolgreich or schluessel in erfolgreich:
            continue
        offen[schluessel] = {"rechnung": v.rechnung, "mahnung": v.mahnung, "grund": v.fehler}
    automatisch = db.session.execute(
        select(Mahnung).where(
            Mahnung.automatisch.is_(True),
            Mahnung.zurueckgezogen_am.is_(None),
            Mahnung.erstellt_am >= seit,
        )
    ).scalars()
    for m in automatisch:
        schluessel = (m.rechnung_id, m.id)
        if schluessel in erfolgreich or schluessel in offen or m.rechnung.offen_cent <= 0:
            continue
        if not any(v.mahnung_id == m.id for v in versuche):
            offen[schluessel] = {
                "rechnung": m.rechnung,
                "mahnung": m,
                "grund": "Keine E-Mail-Adresse beim Kunden oder E-Mail nicht eingerichtet.",
            }
    return [
        eintrag
        for eintrag in offen.values()
        if eintrag["rechnung"] and eintrag["rechnung"].status != "storniert"
    ]
