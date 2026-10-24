"""Beispielrechnung für die Vorschau im Layout-Editor (nichts davon wird gespeichert)."""

from datetime import date, timedelta

from flask import render_template

from app.domain.drucklayout import Layout
from app.domain.iban import formatiere_iban
from app.models import Rechnung, Rechnungsposition
from app.services.einrichtung import aktuelles_gewerbe
from app.services.pdf import layout_kontext
from app.services.rechnungen import absender_daten


def vorschau_html(layout: Layout, bildschirm: bool = True) -> str:
    """Beispielrechnung als HTML, für den Bildschirm (Editor) oder gedruckt (WeasyPrint)."""
    heute = date.today()
    positionen = [
        Rechnungsposition(
            position=1,
            typ="artikel",
            bezeichnung="Fotoshooting",
            beschreibung="Porträts im Studio, inklusive Bildbearbeitung",
            menge_tausendstel=2000,
            einheit="Stunden",
            einzelpreis_cent=6500,
            betrag_cent=13000,
        ),
        Rechnungsposition(position=2, typ="text", bezeichnung="Zusätzliche Leistungen"),
        Rechnungsposition(
            position=3,
            typ="artikel",
            bezeichnung="Anfahrt",
            menge_tausendstel=37000,
            einheit="Kilometer",
            einzelpreis_cent=60,
            betrag_cent=2220,
        ),
    ]
    gewerbe = aktuelles_gewerbe()
    rechnung = Rechnung(
        belegart="rechnung",
        nummer="RE0123",
        rechnungsdatum=heute,
        leistung_art="leistungsdatum",
        leistung_von=heute,
        titel="Rechnung",
        einleitung="Vielen Dank für deinen Auftrag. Wir stellen dir Folgendes in Rechnung.",
        hinweis_steuerbefreiung=gewerbe.hinweis_steuerbefreiung,
        empfaenger_name="Musterfirma GmbH",
        empfaenger_strasse="Musterweg 1",
        empfaenger_plz="12345",
        empfaenger_ort="Musterstadt",
        summe_cent=15220,
    )
    rechnung.positionen = positionen
    absender = absender_daten(gewerbe)
    return render_template(
        "pdf/rechnung.html",
        r=rechnung,
        a=absender,
        iban=formatiere_iban(absender["iban"]) if absender.get("iban") else None,
        qr=None,
        entwurf=False,
        faellig=heute + timedelta(days=14),
        gueltig=heute,
        **layout_kontext(layout, vorschau=bildschirm),
    )
