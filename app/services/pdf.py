"""PDF/A-3b aus HTML mit WeasyPrint (ADR 0008)."""

import io

import segno
from flask import current_app, render_template
from weasyprint import HTML

from app.domain.epc import epc_payload
from app.domain.iban import formatiere_iban
from app.domain.rechnung import faellig_am
from app.models import Rechnung
from app.services.einrichtung import aktuelles_gewerbe


def qr_svg(payload: str) -> str:
    """GiroCode als SVG. Fehlerkorrektur M wie in EPC069-12 vorgesehen."""
    puffer = io.BytesIO()
    segno.make_qr(payload, error="m", encoding="utf-8").save(
        puffer, kind="svg", xmldecl=False, svgns=True, scale=4, border=0
    )
    return puffer.getvalue().decode()


def _qr_fuer(absender: dict, betrag_cent: int, zweck: str) -> str | None:
    if not absender.get("iban") or betrag_cent <= 0:
        return None
    return qr_svg(
        epc_payload(
            name=absender.get("kontoinhaber") or absender["name"],
            iban=absender["iban"],
            bic=absender.get("bic"),
            betrag_cent=betrag_cent,
            verwendungszweck=zweck,
        )
    )


def layout_kontext(layout=None, vorschau: bool = False) -> dict:
    """Aussehen für die PDF-Vorlagen: Layout, Logo (als data:-Adresse) und Logohöhe."""
    from app.services.drucklayout import aktuell, logo_daten_uri, logo_hoehe_mm

    layout = layout or aktuell()
    return {
        "d": layout,
        "logo": logo_daten_uri(),
        "logo_h": logo_hoehe_mm(layout),
        "vorschau": vorschau,
    }


def _als_pdf(html: str) -> bytes:
    return HTML(string=html, base_url=current_app.root_path).write_pdf(pdf_variant="pdf/a-3b")


def rendere_mahnung(rechnung: Rechnung, mahnung, text: str) -> bytes:
    """Mahnung mit QR-Code über den offenen Betrag. Absender wie auf der Rechnung."""
    absender = rechnung.absender
    html = render_template(
        "pdf/mahnung.html",
        r=rechnung,
        m=mahnung,
        text=text,
        a=absender,
        iban=formatiere_iban(absender["iban"]) if absender.get("iban") else None,
        qr=_qr_fuer(absender, mahnung.offen_cent, f"{rechnung.nummer} {mahnung.bezeichnung}"),
        entwurf=False,
        **layout_kontext(),
    )
    return _als_pdf(html)


def rendere_rechnung(rechnung: Rechnung, entwurf: bool) -> bytes:
    from app.services.rechnungen import absender_daten

    absender = rechnung.absender or absender_daten(aktuelles_gewerbe())
    if rechnung.belegart == "lieferschein":
        html = render_template(
            "pdf/lieferschein.html", r=rechnung, a=absender, entwurf=entwurf, **layout_kontext()
        )
        return _als_pdf(html)
    qr = None
    if rechnung.qr_ueberweisung:
        qr = _qr_fuer(absender, rechnung.summe_cent, rechnung.nummer or "Entwurf")
    html = render_template(
        "pdf/rechnung.html",
        r=rechnung,
        a=absender,
        iban=formatiere_iban(absender["iban"]) if absender.get("iban") else None,
        qr=qr,
        entwurf=entwurf,
        faellig=rechnung.faellig_am
        or faellig_am(rechnung.rechnungsdatum, rechnung.zahlungsziel_tage),
        gueltig=rechnung.gueltig_bis
        or faellig_am(rechnung.rechnungsdatum, aktuelles_gewerbe().angebot_gueltig_tage),
        **layout_kontext(),
    )
    return _als_pdf(html)
