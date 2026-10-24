import io
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from weasyprint import HTML

from app.models import Beleg, Buchung, Kategorie, Zahlung
from app.services.belege import neue_belege
from app.services.buchungen import (
    Buchungsdaten,
    erfasse_gebuehren,
    festschreiben,
    lege_entwurf_an,
    offene_gebuehren,
    storniere,
)
from app.services.zahlungen import erfasse_zahlung, kennzahlen, zu_pruefen
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_belegerkennung import TANKBELEG
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

DATEIEN = Path(__file__).parent / "dateien"
HEUTE = date.today()


def text_pdf(inhalt: str) -> bytes:
    html = "<pre style='font-family: monospace'>" + inhalt + "</pre>"  # ohne Unterschneidung
    return HTML(string=html).write_pdf()


def zugferd_pdf() -> bytes:
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(text_pdf("Rechnung siehe Anhang"))))
    writer.add_attachment("factur-x.xml", (DATEIEN / "zugferd_cii.xml").read_bytes())
    puffer = io.BytesIO()
    writer.write(puffer)
    return puffer.getvalue()


def hochladen(client, *dateien):
    daten = {"dateien": [(io.BytesIO(inhalt), name) for name, inhalt in dateien]}
    return client.post("/belege/hochladen", data=daten, content_type="multipart/form-data")


def kategorie(session, name):
    return session.execute(select(Kategorie).where(Kategorie.name == name)).scalar_one()


def ausgabe(session, admin, betrag=4990, prozent=100, kategorie_name="Software und Abos"):
    return lege_entwurf_an(
        Buchungsdaten(
            art="ausgabe",
            belegdatum=HEUTE,
            betrag_cent=betrag,
            kategorie_id=kategorie(session, kategorie_name).id,
            betrieblich_prozent=prozent,
            partner="Software Abo AG",
        ),
        admin.id,
    )


# ---------- Hochladen und Erkennen ----------


def test_text_pdf_wird_ausgelesen(angemeldet, session):
    antwort = hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    beleg = session.execute(select(Beleg)).scalar_one()
    assert antwort.headers["Location"].endswith(f"/belege/{beleg.id}")
    assert beleg.mime == "application/pdf"
    assert beleg.vorschlag["betrag_cent"] == 8117
    assert beleg.vorschlag["lieferant"] == "Muster Tankstelle GmbH"
    seite = angemeldet.get(f"/belege/{beleg.id}").get_data(as_text=True)
    assert "aus dem PDF-Text vorausgefüllt" in seite
    assert 'value="81,17"' in seite
    assert 'value="2026-10-18"' in seite


def test_xrechnung(angemeldet, session):
    hochladen(angemeldet, ("rechnung.xml", (DATEIEN / "xrechnung_ubl.xml").read_bytes()))
    beleg = session.execute(select(Beleg)).scalar_one()
    assert beleg.vorschlag["quelle"] == "xrechnung"
    assert "aus der XRechnung" in angemeldet.get(f"/belege/{beleg.id}").get_data(as_text=True)
    datei = angemeldet.get(f"/belege/{beleg.id}/datei")
    assert datei.mimetype == "text/plain"
    assert "default-src 'none'" in datei.headers["Content-Security-Policy"]


def test_zugferd_anhang(angemeldet, session):
    hochladen(angemeldet, ("zugferd.pdf", zugferd_pdf()))
    beleg = session.execute(select(Beleg)).scalar_one()
    assert beleg.vorschlag["quelle"] == "zugferd"
    assert beleg.vorschlag["betrag_cent"] == 1190


def test_lieferant_wird_kontakt_zugeordnet(angemeldet, session, admin):
    from app.services.kontakte import lege_kontakt_an

    lieferant = lege_kontakt_an(
        {"art": "firma", "firmenname": "Software Abo AG", "typ": "lieferant"}, admin.id
    )
    hochladen(angemeldet, ("abo.xml", (DATEIEN / "zugferd_cii.xml").read_bytes()))
    beleg = session.execute(select(Beleg)).scalar_one()
    seite = angemeldet.get(f"/belege/{beleg.id}").get_data(as_text=True)
    assert f'<option selected value="{lieferant.id}">' in seite


def test_doppelt_und_ungueltig(angemeldet, session):
    inhalt = text_pdf(TANKBELEG)
    hochladen(angemeldet, ("a.pdf", inhalt))
    antwort = hochladen(
        angemeldet, ("b.pdf", inhalt), ("virus.exe", b"MZ\x90\x00"), ("leer.pdf", b"")
    )
    seite = angemeldet.get(antwort.headers["Location"]).get_data(as_text=True)
    assert "bereits hochgeladen" in seite
    assert "Nur PDF, JPG, PNG und XML" in seite
    assert "Die Datei ist leer" in seite
    assert len(session.execute(select(Beleg)).all()) == 1


def test_mehrere_auf_einmal(angemeldet, session):
    antwort = hochladen(
        angemeldet,
        ("a.pdf", text_pdf(TANKBELEG)),
        ("b.xml", (DATEIEN / "xrechnung_ubl.xml").read_bytes()),
        ("c.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20),
    )
    assert "filter=pruefen" in antwort.headers["Location"]
    assert len(neue_belege()) == 3


# ---------- Erfassen, Festschreiben, Zahlen ----------


def formular(session, **mehr):
    daten = {
        "art": "ausgabe",
        "partner": "Muster Tankstelle GmbH",
        "belegdatum": "2026-10-18",
        "belegnummer": "2026-10-77",
        "betrag": "81,17",
        "kategorie_id": str(kategorie(session, "Fahrzeugkosten").id),
        "betrieblich_prozent": "100",
        "zahlungsart": "karte",
        "aktion": "festschreiben",
    }
    daten.update(mehr)
    return {k: v for k, v in daten.items() if v is not None}


def test_erfassen_und_bezahlt_festschreiben(angemeldet, session):
    hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    beleg = session.execute(select(Beleg)).scalar_one()
    antwort = angemeldet.post(
        f"/belege/{beleg.id}",
        data=formular(session, bereits_bezahlt="y", bezahlt_am="2026-10-18"),
    )
    assert antwort.status_code == 302
    buchung = session.execute(select(Buchung)).scalar_one()
    assert (buchung.status, buchung.zahlstatus, buchung.beleg_id) == (
        "festgeschrieben",
        "bezahlt",
        beleg.id,
    )
    assert buchung.zahlungen[0].zahlungsart == "karte"
    assert neue_belege() == []
    assert kennzahlen(2026)["ausgaben_cent"] == 8117
    # Der Beleg führt jetzt zur Buchung
    assert (
        angemeldet.get(f"/belege/{beleg.id}")
        .headers["Location"]
        .endswith(f"/buchungen/{buchung.id}")
    )


def test_beleg_nur_einmal_buchen(angemeldet, session):
    hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    beleg = session.execute(select(Beleg)).scalar_one()
    daten = formular(session, bereits_bezahlt="y", bezahlt_am="2026-10-18")
    angemeldet.post(f"/belege/{beleg.id}", data=daten)
    # zweiter Absenden (Doppelklick, zweiter Tab) darf nicht doppelt buchen
    antwort = angemeldet.post(f"/belege/{beleg.id}", data={**daten, "betrag": "5,00"})
    assert antwort.status_code == 302
    assert len(session.execute(select(Buchung)).all()) == 1
    assert kennzahlen(2026)["ausgaben_cent"] == 8117


def test_beleg_nach_storno_erneut_buchbar(angemeldet, session):
    hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    beleg = session.execute(select(Beleg)).scalar_one()
    daten = formular(session, bereits_bezahlt="y", bezahlt_am="2026-10-18")
    angemeldet.post(f"/belege/{beleg.id}", data=daten)
    erste = session.execute(select(Buchung)).scalar_one()
    angemeldet.post(f"/buchungen/{erste.id}/stornieren")
    antwort = angemeldet.post(f"/belege/{beleg.id}", data={**daten, "betrag": "90,00"})
    assert antwort.status_code == 302
    assert len(session.execute(select(Buchung).where(Buchung.betrag_cent == 9000)).all()) == 1


def test_bezahlt_ohne_datum(angemeldet, session):
    daten = formular(session, bereits_bezahlt="y", bezahlt_am="")  # Formular sendet das Feld leer
    antwort = angemeldet.post("/buchungen/neu", data=daten)
    assert antwort.status_code == 422
    assert "Bitte das Zahlungsdatum angeben" in antwort.get_data(as_text=True)


def test_kategorie_muss_passen(angemeldet, session):
    daten = formular(session, art="einnahme")
    antwort = angemeldet.post("/buchungen/neu", data=daten)
    assert antwort.status_code == 422
    assert "passt nicht zur Art" in antwort.get_data(as_text=True)


def test_festschreiben_braucht_kategorie(angemeldet, session):
    antwort = angemeldet.post("/buchungen/neu", data=formular(session, kategorie_id=""))
    assert "Kategorie" in antwort.get_data(as_text=True)
    assert session.execute(select(Buchung)).first() is None


def test_entwurf_bearbeiten_und_loeschen(angemeldet, session):
    angemeldet.post("/buchungen/neu", data=formular(session, aktion="speichern"))
    buchung = session.execute(select(Buchung)).scalar_one()
    assert buchung.status == "entwurf"
    assert buchung in zu_pruefen()["buchungsentwuerfe"]
    angemeldet.post(
        f"/buchungen/{buchung.id}", data=formular(session, aktion="speichern", betrag="90,00")
    )
    assert buchung.betrag_cent == 9000
    assert angemeldet.post(f"/buchungen/{buchung.id}/loeschen").status_code == 302
    assert session.execute(select(Buchung)).first() is None


def test_unbezahlt_dann_zahlung(angemeldet, session, admin):
    angemeldet.post("/buchungen/neu", data=formular(session))
    buchung = session.execute(select(Buchung)).scalar_one()
    assert buchung.zahlstatus == "offen"
    assert buchung in zu_pruefen()["offene_ausgaben"]
    antwort = angemeldet.post(
        f"/buchungen/{buchung.id}/zahlungen",
        data={"datum": "2026-10-20", "betrag": "81,17", "zahlungsart": "ueberweisung"},
    )
    assert antwort.status_code == 302
    assert buchung.zahlstatus == "bezahlt"
    assert zu_pruefen()["offene_ausgaben"] == []


def test_privatanteil(session, admin):
    buchung = ausgabe(
        session, admin, betrag=4000, prozent=50, kategorie_name="Telefon und Internet"
    )
    festschreiben(buchung, admin.id, bezahlt_am=HEUTE, zahlungsart="ueberweisung")
    assert kennzahlen(HEUTE.year)["ausgaben_cent"] == 2000


def test_einnahme_ohne_rechnung(session, admin):
    buchung = lege_entwurf_an(
        Buchungsdaten(
            art="einnahme",
            belegdatum=HEUTE,
            betrag_cent=2500,
            kategorie_id=kategorie(session, "Umsatzerlöse").id,
            partner="Barverkauf Markt",
        ),
        admin.id,
    )
    festschreiben(buchung, admin.id, bezahlt_am=HEUTE, zahlungsart="bar")
    assert kennzahlen(HEUTE.year)["einnahmen_cent"] == 2500


# ---------- Storno und Unveränderlichkeit ----------


def test_storno(session, admin, angemeldet):
    hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    beleg = session.execute(select(Beleg)).scalar_one()
    angemeldet.post(
        f"/belege/{beleg.id}", data=formular(session, bereits_bezahlt="y", bezahlt_am="2026-10-18")
    )
    buchung = session.execute(select(Buchung)).scalar_one()
    assert angemeldet.post(f"/buchungen/{buchung.id}/stornieren").status_code == 302
    assert buchung.zahlstatus == "storniert"
    gegen = buchung.storno
    assert gegen.betrag_cent == -8117 and gegen.storno_von_id == buchung.id
    assert sum(z.betrag_cent for z in buchung.zahlungen) == 0
    assert kennzahlen(2026)["ausgaben_cent"] == 0
    # Beleg kann neu verbucht werden
    assert angemeldet.get(f"/belege/{beleg.id}").status_code == 200
    with pytest.raises(Exception, match="bereits storniert"):
        storniere(buchung, admin.id)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE buchung SET betrag_cent = 1",
        "DELETE FROM buchung",
    ],
)
def test_festgeschriebene_buchung_unveraenderlich(session, admin, sql):
    festschreiben(ausgabe(session, admin), admin.id)
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text(sql))


@pytest.mark.parametrize(
    ("sql", "meldung"),
    [
        ("DELETE FROM beleg", "nie gelöscht"),
        ("UPDATE beleg SET sha256 = 'x'", "unveränderlich"),
        ("UPDATE beleg SET dateiname = 'anders.pdf'", "unveränderlich"),
    ],
)
def test_beleg_unveraenderlich(angemeldet, session, sql, meldung):
    hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    with pytest.raises(DBAPIError, match=meldung), session.begin_nested():
        session.execute(text(sql))


def test_zahlung_nur_zu_festgeschriebener_buchung(session, admin):
    entwurf = ausgabe(session, admin)
    with pytest.raises(DBAPIError, match="festgeschriebenen"), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO zahlung (buchung_id, datum, betrag_cent, zahlungsart, erfasst_von) "
                f"VALUES ({entwurf.id}, CURRENT_DATE, 100, 'bar', {admin.id})"
            )
        )


def test_verwerfen(angemeldet, session):
    hochladen(angemeldet, ("falsch.pdf", text_pdf("Privat Quittung 3,50 €")))
    beleg = session.execute(select(Beleg)).scalar_one()
    assert angemeldet.post(f"/belege/{beleg.id}/verwerfen").status_code == 302
    assert beleg.verworfen and neue_belege() == []
    assert "falsch.pdf" in angemeldet.get("/belege?filter=verworfen").get_data(as_text=True)


def test_verbuchter_beleg_nicht_verwerfbar(angemeldet, session):
    hochladen(angemeldet, ("tanken.pdf", text_pdf(TANKBELEG)))
    beleg = session.execute(select(Beleg)).scalar_one()
    angemeldet.post(f"/belege/{beleg.id}", data=formular(session))
    angemeldet.post(f"/belege/{beleg.id}/verwerfen")
    assert not beleg.verworfen


# ---------- Gebühren ----------


def test_gebuehren_als_ausgabe(rechnung, admin, session, angemeldet):  # noqa: F811
    zahlung = erfasse_zahlung(
        rechnung,
        datum=HEUTE,
        betrag_cent=15220,
        zahlungsart="paypal",
        angekommen_cent=14750,
        notiz=None,
        nutzer_id=admin.id,
    )
    assert offene_gebuehren() == [zahlung]
    seite = angemeldet.get("/buchungen/gebuehren").get_data(as_text=True)
    assert "4,70 €" in seite
    antwort = angemeldet.post("/buchungen/gebuehren", data={"zahlung": str(zahlung.id)})
    assert antwort.status_code == 302
    gebuehr = session.execute(select(Buchung)).scalar_one()
    assert (gebuehr.betrag_cent, gebuehr.kategorie.name, gebuehr.zahlstatus) == (
        470,
        "Gebühren",
        "bezahlt",
    )
    assert gebuehr.zahlungen[0].datum == zahlung.datum
    assert offene_gebuehren() == []
    assert kennzahlen(HEUTE.year)["ausgaben_cent"] == 470
    # Nach einem Storno ist die Gebühr wieder offen
    storniere(gebuehr, admin.id)
    assert offene_gebuehren() == [zahlung]
    assert erfasse_gebuehren([zahlung.id], admin.id).betrag_cent == 470


# ---------- Rechte und Oberfläche ----------


def test_mitarbeiter_nur_entwurf(client, admin, session):
    neuer_nutzer(session, "m@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "m@x.example", "passwort": ADMIN_PASSWORT})
    assert hochladen(client, ("tanken.pdf", text_pdf(TANKBELEG))).status_code == 302
    beleg = session.execute(select(Beleg)).scalar_one()
    client.post(f"/belege/{beleg.id}", data=formular(session))  # will festschreiben
    buchung = session.execute(select(Buchung)).scalar_one()
    assert buchung.status == "entwurf"
    assert client.post(f"/buchungen/{buchung.id}/stornieren").status_code == 403


def test_steuerberater_nur_lesen(client, admin, session):
    festschreiben(ausgabe(session, admin), admin.id)
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    client.post("/anmelden", data={"email": "stb@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/belege?filter=ausgaben").status_code == 200
    assert hochladen(client, ("x.pdf", text_pdf(TANKBELEG))).status_code == 403
    assert client.get("/buchungen/neu").status_code == 403


def test_liste_und_dashboard(angemeldet, session, admin):
    festschreiben(ausgabe(session, admin), admin.id, bezahlt_am=HEUTE, zahlungsart="karte")
    liste = angemeldet.get("/belege?filter=ausgaben").get_data(as_text=True)
    assert "Software Abo AG" in liste and "49,90 €" in liste
    start = angemeldet.get("/").get_data(as_text=True)
    assert "49,90 €" in start  # Ausgaben in der Übersicht
    assert "var(--rot)" in start  # Ausgabenlinie im Diagramm


def test_gwg_hinweis(angemeldet, session):
    antwort = angemeldet.post(
        "/buchungen/neu", data=formular(session, betrag="1.299,00", kategorie_id="")
    )
    assert "Über 952 € brutto" in antwort.get_data(as_text=True)


def test_zahlung_hat_genau_einen_bezug(session, admin):
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO zahlung (datum, betrag_cent, zahlungsart, erfasst_von) "
                f"VALUES (CURRENT_DATE, 100, 'bar', {admin.id})"
            )
        )
    assert session.execute(select(Zahlung)).first() is None


def test_ausgabe_in_einnahme_kategorie_wird_abgewiesen(angemeldet, session):
    """Art und Kategorie müssen zusammenpassen, sonst landet eine Ausgabe in den Einnahmen."""
    from sqlalchemy import select as sql_select

    from app.models import Buchung, Kategorie

    einnahme = session.execute(
        sql_select(Kategorie.id).where(Kategorie.name == "Umsatzerlöse")
    ).scalar_one()
    antwort = angemeldet.post(
        "/buchungen/neu",
        data={
            "art": "ausgabe",
            "kontakt_id": "",
            "partner": "Test",
            "belegdatum": "2026-03-01",
            "betrag": "10,00",
            "betrieblich_prozent": "100",
            "kategorie_id": str(einnahme),
            "aktion": "speichern",
        },
    )
    assert session.execute(sql_select(Buchung)).first() is None, (
        "Eine Ausgabe mit Einnahme-Kategorie wurde gespeichert"
    )
    assert antwort.status_code in (200, 422)


def test_belegdatum_weit_in_der_zukunft_abgelehnt(angemeldet, session):
    from datetime import timedelta

    weit = (HEUTE + timedelta(days=400)).isoformat()
    antwort = angemeldet.post("/buchungen/neu", data=formular(session, belegdatum=weit))
    assert antwort.status_code == 422
    assert "Tage in der Zukunft" in antwort.get_data(as_text=True)
    assert session.execute(select(Buchung)).first() is None
    bald = (HEUTE + timedelta(days=10)).isoformat()
    assert (
        angemeldet.post("/buchungen/neu", data=formular(session, belegdatum=bald)).status_code
        == 302
    )
