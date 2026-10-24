import io
from datetime import date

import pytest
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import Gewerbe, Protokoll, Rechnung
from app.services import ablage
from app.services.artikel import lege_artikel_an
from app.services.kontakte import lege_kontakt_an
from app.services.rechnungen import (
    NichtBearbeitbar,
    NichtFinalisierbar,
    finalisiere,
    loesche_entwurf,
    neuer_entwurf,
)
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

IBAN = "DE89370400440532013000"


@pytest.fixture
def bank(admin, session):
    gewerbe = session.get(Gewerbe, 1)
    gewerbe.iban = IBAN
    gewerbe.bank = "Musterbank"
    session.commit()
    return gewerbe


@pytest.fixture
def kunde(admin):
    return lege_kontakt_an(
        {
            "art": "firma",
            "firmenname": "Café Sonnenschein",
            "typ": "kunde",
            "strasse": "Markt 5",
            "plz": "50667",
            "ort": "Köln",
        },
        admin.id,
    )


@pytest.fixture
def auftritt(admin):
    return lege_artikel_an(
        {"typ": "service", "bezeichnung": "Auftritt", "einheit": "Stunde", "preis_cent": 6500},
        admin.id,
    )


def formular(rechnung, kunde, **mehr):
    daten = {
        "kontakt_id": str(kunde.id),
        # Das Formular schickt die angezeigte Anschrift immer mit
        "empfaenger_name": kunde.name,
        "empfaenger_strasse": kunde.strasse,
        "empfaenger_plz": kunde.plz,
        "empfaenger_ort": kunde.ort,
        "rechnungsdatum": "2026-10-21",
        "leistung_art": "leistungsdatum",
        "leistung_von": "2026-10-18",
        "titel": "Rechnung",
        "hinweis_steuerbefreiung": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        "zahlungsziel_tage": "14",
        "angebot_gueltig_tage": "30",
        "qr_ueberweisung": "y",
        "pos-0-typ": "artikel",
        "pos-0-bezeichnung": "Auftritt",
        "pos-0-menge": "2",
        "pos-0-einheit": "Stunde",
        "pos-0-preis": "65,00",
        "pos-1-typ": "text",
        "pos-1-bezeichnung": "Zusatzleistungen",
        "pos-2-typ": "artikel",
        "pos-2-bezeichnung": "Anfahrt",
        "pos-2-menge": "37",
        "pos-2-einheit": "Kilometer",
        "pos-2-preis": "0,60",
        "pos-2-rabatt": "",
        "aktion": "speichern",
    }
    daten.update(mehr)
    return {k: v for k, v in daten.items() if v is not None}


def speichern(client, rechnung, kunde, **mehr):
    return client.post(
        f"/rechnungen/{rechnung.id}/bearbeiten", data=formular(rechnung, kunde, **mehr)
    )


@pytest.fixture
def entwurf(angemeldet, admin, kunde, bank):
    rechnung = neuer_entwurf(admin.id)
    assert speichern(angemeldet, rechnung, kunde).status_code == 302
    return rechnung


def pdf_text(inhalt: bytes) -> str:
    return "\n".join(seite.extract_text() for seite in PdfReader(io.BytesIO(inhalt)).pages)


# ---------- Entwurf ----------


def test_neuer_entwurf_mit_vorgaben(angemeldet, session, bank):
    bank.rechnung_einleitung = "Vielen Dank für den Auftrag."
    session.commit()
    antwort = angemeldet.post("/rechnungen/neu")
    rechnung = session.execute(select(Rechnung)).scalar_one()
    assert antwort.headers["Location"].endswith(f"/rechnungen/{rechnung.id}/bearbeiten")
    assert rechnung.status == "entwurf" and rechnung.nummer is None
    assert rechnung.einleitung == "Vielen Dank für den Auftrag."
    assert "§ 19" in rechnung.hinweis_steuerbefreiung
    assert rechnung.qr_ueberweisung  # IBAN vorhanden
    assert angemeldet.get(f"/rechnungen/{rechnung.id}/bearbeiten").status_code == 200


def test_speichern_berechnet_und_uebernimmt_anschrift(entwurf, kunde):
    assert entwurf.empfaenger_name == "Café Sonnenschein"
    assert entwurf.empfaenger_ort == "Köln"
    assert [p.betrag_cent for p in entwurf.positionen] == [13000, 0, 2220]
    assert entwurf.summe_cent == 15220


def test_eigene_anschrift_bleibt_wenn_kunde_gleich(angemeldet, entwurf, kunde):
    speichern(angemeldet, entwurf, kunde, empfaenger_zusatz="z. Hd. Frau Sonne")
    assert entwurf.empfaenger_zusatz == "z. Hd. Frau Sonne"


def test_fehlerhafte_eingabe_speichert_nichts(angemeldet, entwurf, kunde):
    antwort = speichern(angemeldet, entwurf, kunde, **{"pos-0-preis": "abc"})
    assert antwort.status_code == 422
    assert "Ungültiger Preis" in antwort.get_data(as_text=True)
    assert entwurf.summe_cent == 15220


@pytest.mark.parametrize(
    ("aktion", "anzahl", "letzte"),
    [("position", 4, "artikel"), ("freitext", 4, "text"), ("entfernen-1", 2, "artikel")],
)
def test_positionen_hinzufuegen_entfernen(angemeldet, entwurf, kunde, aktion, anzahl, letzte):
    speichern(angemeldet, entwurf, kunde, aktion=aktion)
    assert len(entwurf.positionen) == anzahl
    assert entwurf.positionen[-1].typ == letzte


def test_artikel_ersetzt_leere_position(angemeldet, admin, kunde, auftritt, bank):
    rechnung = neuer_entwurf(admin.id)
    daten = formular(rechnung, kunde, aktion="artikel", neuer_artikel=str(auftritt.id))
    for feld in ("bezeichnung", "menge", "einheit", "preis"):
        daten[f"pos-0-{feld}"] = ""
    daten = {k: v for k, v in daten.items() if not k.startswith(("pos-1", "pos-2"))}
    angemeldet.post(f"/rechnungen/{rechnung.id}/bearbeiten", data=daten)
    assert [p.bezeichnung for p in rechnung.positionen] == ["Auftritt"]


def test_artikel_hinzufuegen(angemeldet, entwurf, kunde, auftritt):
    speichern(angemeldet, entwurf, kunde, aktion="artikel", neuer_artikel=str(auftritt.id))
    neu = entwurf.positionen[-1]
    assert (neu.bezeichnung, neu.einzelpreis_cent, neu.artikel_id) == (
        "Auftritt",
        6500,
        auftritt.id,
    )


def test_entwurf_loeschen(angemeldet, entwurf, session):
    assert angemeldet.post(f"/rechnungen/{entwurf.id}/loeschen").status_code == 302
    assert session.execute(select(Rechnung)).first() is None


def test_vorschau_zeigt_fehlende_angaben(angemeldet, entwurf, kunde):
    speichern(angemeldet, entwurf, kunde, leistung_von="")
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/vorschau").get_data(as_text=True)
    assert "Liefer- oder Leistungsdatum fehlt" in seite


def test_entwurf_pdf_mit_wasserzeichen(angemeldet, entwurf):
    antwort = angemeldet.get(f"/rechnungen/{entwurf.id}/pdf")
    assert antwort.mimetype == "application/pdf"
    assert "ENTWURF" in pdf_text(antwort.data)


# ---------- Finalisieren ----------


def test_finalisieren(angemeldet, entwurf, session, admin):
    antwort = angemeldet.post(f"/rechnungen/{entwurf.id}/finalisieren")
    assert antwort.status_code == 302
    assert entwurf.nummer == "RE0001"
    assert entwurf.status == "offen"
    assert entwurf.faellig_am == date(2026, 11, 4)
    assert entwurf.absender["iban"] == IBAN
    assert entwurf.finalisiert_von == admin.id
    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "rechnung_finalisiert")
    ).scalar_one()
    assert eintrag.details["nummer"] == "RE0001"


def test_pdf_inhalt(angemeldet, entwurf):
    angemeldet.post(f"/rechnungen/{entwurf.id}/finalisieren")
    inhalt = angemeldet.get(f"/rechnungen/{entwurf.id}/pdf").data
    assert inhalt.startswith(b"%PDF")
    metadaten = PdfReader(io.BytesIO(inhalt)).trailer["/Root"]["/Metadata"].get_object()
    assert b"pdfaid:part" in metadaten.get_data()  # PDF/A-Kennung
    text_ = pdf_text(inhalt)
    for erwartet in [
        "Rechnung RE0001",
        "Café Sonnenschein",
        "Markt 5",
        "Leistungsdatum",
        "18.10.2026",
        "152,20 €",
        "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        "DE89 3704 0044 0532 0130 00",
        "Mit Banking-App scannen",
        "04.11.2026",
    ]:
        assert erwartet in text_, erwartet
    assert "ENTWURF" not in text_


def test_nummern_fortlaufend_und_fortsetzbar(angemeldet, admin, kunde, bank, session, app):
    from app.models import Nummernkreis

    session.get(Nummernkreis, "rechnung").naechste_nummer = 131
    session.commit()
    nummern = []
    for _ in range(2):
        rechnung = neuer_entwurf(admin.id)
        speichern(angemeldet, rechnung, kunde)
        with app.app_context():
            nummern.append(finalisiere(rechnung, admin.id).nummer)
    assert nummern == ["RE0131", "RE0132"]


def test_qr_braucht_bankverbindung(angemeldet, admin, kunde, session, app):
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde)
    with app.app_context(), pytest.raises(NichtFinalisierbar) as fehler:
        finalisiere(rechnung, admin.id)
    assert any("Bankverbindung" in f for f in fehler.value.fehler)
    speichern(angemeldet, rechnung, kunde, qr_ueberweisung=None)
    with app.app_context():
        assert finalisiere(rechnung, admin.id).nummer == "RE0001"


@pytest.mark.parametrize(
    ("aenderung", "meldung"),
    [
        ({"leistung_art": "leistungszeitraum", "leistung_bis": ""}, "Ende des Leistungszeitraums"),
        (
            {"leistung_art": "leistungszeitraum", "leistung_bis": "2026-10-01"},
            "endet vor seinem Beginn",
        ),
        ({"hinweis_steuerbefreiung": ""}, "Hinweis auf die Steuerbefreiung"),
        ({"pos-0-bezeichnung": ""}, "Bezeichnung"),
        ({"kontakt_id": "", "empfaenger_name": ""}, "Empfänger"),
        ({"pos-0-preis": "-500,00"}, "nicht negativ"),
    ],
)
def test_finalisieren_prueft_pflichtangaben(
    angemeldet, admin, kunde, bank, aenderung, meldung, app
):
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde)
    speichern(angemeldet, rechnung, kunde, **aenderung)
    with app.app_context(), pytest.raises(NichtFinalisierbar) as fehler:
        finalisiere(rechnung, admin.id)
    assert any(meldung in f for f in fehler.value.fehler)
    assert rechnung.nummer is None


def test_leistungszeitraum_im_pdf(angemeldet, admin, kunde, bank, app):
    rechnung = neuer_entwurf(admin.id)
    speichern(
        angemeldet, rechnung, kunde, leistung_art="leistungszeitraum", leistung_bis="2026-10-20"
    )
    with app.app_context():
        finalisiere(rechnung, admin.id)
    assert "18.10.2026 – 20.10.2026" in pdf_text(
        angemeldet.get(f"/rechnungen/{rechnung.id}/pdf").data
    )


# ---------- Unveränderlichkeit ----------


@pytest.fixture
def final(angemeldet, entwurf):
    angemeldet.post(f"/rechnungen/{entwurf.id}/finalisieren")
    return entwurf


def test_finalisiert_nicht_mehr_bearbeitbar(angemeldet, final, kunde, admin, app):
    assert angemeldet.get(f"/rechnungen/{final.id}/bearbeiten").status_code == 302
    speichern(angemeldet, final, kunde, **{"pos-0-preis": "1,00"})
    assert final.summe_cent == 15220
    with app.app_context(), pytest.raises(NichtBearbeitbar):
        loesche_entwurf(final, admin.id)
    assert angemeldet.post(f"/rechnungen/{final.id}/loeschen").status_code == 409


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE rechnung SET summe_cent = 1",
        "UPDATE rechnung SET empfaenger_name = 'Jemand anderes'",
        "UPDATE rechnung SET status = 'entwurf'",
        "DELETE FROM rechnung",
        "UPDATE rechnungsposition SET einzelpreis_cent = 1",
        "DELETE FROM rechnungsposition",
        "INSERT INTO rechnungsposition (rechnung_id, position, typ, bezeichnung, "
        "menge_tausendstel, einzelpreis_cent, rabatt_bp, betrag_cent) "
        "SELECT id, 9, 'artikel', 'x', 1000, 1, 0, 1 FROM rechnung",
    ],
)
def test_datenbank_schuetzt_finalisierte_rechnung(final, session, sql):
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text(sql))


def test_status_darf_sich_aendern(final, session):
    session.execute(text("UPDATE rechnung SET status = 'bezahlt'"))
    session.commit()
    session.refresh(final)
    assert final.status == "bezahlt"


def test_kontaktaenderung_aendert_rechnung_nicht(angemeldet, final, kunde):
    angemeldet.post(
        f"/kontakte/{kunde.id}/bearbeiten",
        data={"art": "firma", "firmenname": "Neuer Name", "typ": "kunde", "land": "Deutschland"},
    )
    assert final.empfaenger_name == "Café Sonnenschein"
    assert "Café Sonnenschein" in pdf_text(angemeldet.get(f"/rechnungen/{final.id}/pdf").data)


def test_pdf_wird_nicht_neu_erzeugt(angemeldet, final, session, app):
    gewerbe = session.get(Gewerbe, 1)
    gewerbe.name = "Umbenannt GmbH"
    session.commit()
    inhalt = angemeldet.get(f"/rechnungen/{final.id}/pdf").data
    assert "Umbenannt" not in pdf_text(inhalt)


def test_veraenderte_pdf_wird_erkannt(final, app):
    with app.app_context():
        pfad = ablage._pfad(final.pdf_sha256)
        original = pfad.read_bytes()
        pfad.chmod(0o644)
        try:
            pfad.write_bytes(b"manipuliert")
            with pytest.raises(ablage.AblageBeschaedigt):
                ablage.lies(final.pdf_sha256)
        finally:
            pfad.write_bytes(original)
            pfad.chmod(0o444)


# ---------- Liste und Rechte ----------


def test_liste_mit_filter(angemeldet, final, admin, kunde):
    neuer_entwurf(admin.id)
    alle = angemeldet.get("/rechnungen").get_data(as_text=True)
    assert "RE0001" in alle and "Entwurf" in alle
    offen = angemeldet.get("/rechnungen?filter=offen").get_data(as_text=True)
    assert "RE0001" in offen and "Entwurf</a>" not in offen


def test_mitarbeiter_entwurf_ja_finalisieren_nein(client, admin, kunde, bank, session):
    neuer_nutzer(session, "m@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "m@x.example", "passwort": ADMIN_PASSWORT})
    antwort = client.post("/rechnungen/neu")
    assert antwort.status_code == 302
    rechnung = session.execute(select(Rechnung)).scalar_one()
    speichern(client, rechnung, kunde)
    assert client.post(f"/rechnungen/{rechnung.id}/finalisieren").status_code == 403
    assert "Finalisieren darf deine Rolle nicht" in client.get(
        f"/rechnungen/{rechnung.id}/vorschau"
    ).get_data(as_text=True)


def test_steuerberater_sieht_pdf(client, final, session):
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    client.post("/abmelden")  # der Client aus `final` ist noch als Admin angemeldet
    client.post("/anmelden", data={"email": "stb@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/rechnungen").status_code == 200
    assert client.get(f"/rechnungen/{final.id}").status_code == 200
    assert client.get(f"/rechnungen/{final.id}/pdf").status_code == 200
    assert client.post("/rechnungen/neu").status_code == 403


# ---------- Einstellungen ----------


def test_rechnungseinstellungen(angemeldet, session):
    daten = {
        "kontoinhaber": "Erika Mustermann",
        "iban": "de89 3704 0044 0532 0130 00",
        "bic": "cobadeffxxx",
        "bank": "Musterbank",
        "praefix": "RE",
        "stellen": "4",
        "naechste_nummer": "131",
        "zahlungsziel_tage": "10",
        "angebot_gueltig_tage": "30",
        "hinweis_steuerbefreiung": "Umsatzsteuerfreie Leistungen gemäß § 19 UStG.",
    }
    assert angemeldet.post("/einstellungen/rechnungen", data=daten).status_code == 302
    gewerbe = session.get(Gewerbe, 1)
    assert (gewerbe.iban, gewerbe.bic, gewerbe.zahlungsziel_tage) == (IBAN, "COBADEFFXXX", 10)


@pytest.mark.parametrize(
    ("aenderung", "meldung"),
    [
        ({"iban": "DE89370400440532013001"}, "Prüfziffer"),
        ({"bic": "ABC"}, "8 oder 11 Zeichen"),
        ({"hinweis_steuerbefreiung": "Steuerfrei."}, "§ 19 UStG nennen"),
        ({"naechste_nummer": "0"}, "Mindestens 1"),
    ],
)
def test_rechnungseinstellungen_pruefen(angemeldet, aenderung, meldung):
    daten = {
        "praefix": "RE",
        "stellen": "4",
        "naechste_nummer": "1",
        "zahlungsziel_tage": "14",
        "angebot_gueltig_tage": "30",
        "hinweis_steuerbefreiung": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        **aenderung,
    }
    antwort = angemeldet.post("/einstellungen/rechnungen", data=daten)
    assert meldung in antwort.get_data(as_text=True)


def test_vergebene_nummer_nicht_erneut(angemeldet, final):
    daten = {
        "praefix": "RE",
        "stellen": "4",
        "naechste_nummer": "1",
        "zahlungsziel_tage": "14",
        "angebot_gueltig_tage": "30",
        "hinweis_steuerbefreiung": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        "iban": IBAN,
    }
    antwort = angemeldet.post("/einstellungen/rechnungen", data=daten)
    assert "RE0001 ist schon vergeben" in antwort.get_data(as_text=True)
