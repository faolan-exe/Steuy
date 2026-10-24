import io
from datetime import date, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.domain.zahlung import ZahlungUngueltig
from app.models import Rechnung
from app.services.mahnwesen import MahnungNichtMoeglich, erstelle_mahnung, faellige_mahnungen
from app.services.rechnungen import (
    AktionNichtMoeglich,
    entscheide_angebot,
    finalisiere,
    neuer_entwurf,
    storniere_rechnung,
    suche_rechnungen,
)
from app.services.zahlungen import erfasse_zahlung, kennzahlen, zu_pruefen
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()


def pdf_text(inhalt: bytes) -> str:
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(inhalt)).pages)


@pytest.fixture
def angebot(angemeldet, admin, kunde, bank, app):  # noqa: F811
    entwurf = neuer_entwurf(admin.id, "angebot")
    speichern(
        angemeldet,
        entwurf,
        kunde,
        rechnungsdatum=HEUTE.isoformat(),
        leistung_von="",
        qr_ueberweisung=None,
        titel="Angebot",
    )
    with app.app_context():
        return finalisiere(entwurf, admin.id)


# ---------- Angebote ----------


def test_angebot_nummer_und_gueltigkeit(angebot):
    assert angebot.belegart == "angebot"
    assert angebot.nummer == "AN0001"
    assert angebot.gueltig_bis == HEUTE + timedelta(days=30)
    assert angebot.faellig_am is None
    assert angebot.qr_ueberweisung is False
    assert angebot.status == "offen"


def test_angebot_pdf(angemeldet, angebot):
    inhalt = pdf_text(angemeldet.get(f"/rechnungen/{angebot.id}/pdf").data)
    assert "Angebot AN0001" in inhalt
    assert "gültig bis zum" in inhalt
    assert (HEUTE + timedelta(days=30)).strftime("%d.%m.%Y") in inhalt
    assert "Mit Banking-App" not in inhalt
    assert "Bitte überweisen" not in inhalt


def test_angebot_ueber_oberflaeche(angemeldet, session):
    antwort = angemeldet.post("/angebote/neu")
    angebot = session.execute(select(Rechnung)).scalar_one()
    assert angebot.belegart == "angebot" and angebot.titel == "Angebot"
    seite = angemeldet.get(antwort.headers["Location"]).get_data(as_text=True)
    assert "Angebot erstellen" in seite
    assert "Überweisung mit QR-Code" not in seite


def test_angebotsliste_getrennt(angemeldet, angebot, rechnung):  # noqa: F811
    angebote = angemeldet.get("/angebote").get_data(as_text=True)
    rechnungen = angemeldet.get("/rechnungen").get_data(as_text=True)
    assert "AN0001" in angebote and rechnung.nummer not in angebote
    assert rechnung.nummer in rechnungen and "AN0001" not in rechnungen


def test_angebot_annehmen_und_ablehnen(angemeldet, angebot, admin):
    assert angebot in zu_pruefen()["angebote"]
    angemeldet.post(f"/rechnungen/{angebot.id}/ablehnen")
    assert angebot.status == "abgelehnt"
    assert angebot not in zu_pruefen()["angebote"]
    entscheide_angebot(angebot, True, admin.id)
    assert angebot.status == "angenommen"


def test_angebot_in_rechnung(angemeldet, angebot, session):
    antwort = angemeldet.post(f"/rechnungen/{angebot.id}/in-rechnung")
    neu = session.execute(select(Rechnung).where(Rechnung.belegart == "rechnung")).scalar_one()
    assert antwort.headers["Location"].endswith(f"/rechnungen/{neu.id}/bearbeiten")
    assert neu.status == "entwurf" and neu.bezug_id == angebot.id
    assert neu.empfaenger_name == angebot.empfaenger_name
    assert [p.bezeichnung for p in neu.positionen] == [p.bezeichnung for p in angebot.positionen]
    assert neu.summe_cent == angebot.summe_cent
    assert angebot.status == "angenommen"


def test_angebot_keine_zahlung_keine_mahnung(angebot, admin, app):
    with pytest.raises(ZahlungUngueltig):
        erfasse_zahlung(
            angebot,
            datum=HEUTE,
            betrag_cent=100,
            zahlungsart="bar",
            angekommen_cent=None,
            notiz=None,
            nutzer_id=admin.id,
        )
    with app.app_context(), pytest.raises(MahnungNichtMoeglich):
        erstelle_mahnung(angebot, admin.id)
    assert faellige_mahnungen(heute=HEUTE + timedelta(days=400)) == []


def test_db_keine_zahlung_zu_angebot(angebot, admin, session):
    with pytest.raises(DBAPIError, match="finalisierten Rechnungen"), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO zahlung (rechnung_id, datum, betrag_cent, zahlungsart, erfasst_von) "
                f"VALUES ({angebot.id}, CURRENT_DATE, 100, 'bar', {admin.id})"
            )
        )


def test_kennzahlen_trennen(angebot, rechnung):  # noqa: F811
    werte = kennzahlen(HEUTE.year)
    assert werte["anzahl_angebote"] == 1
    assert werte["anzahl_rechnungen"] == 1
    assert werte["offen_cent"] == rechnung.summe_cent


# ---------- Rechnungskorrektur ----------


def test_storno_erzeugt_korrektur(rechnung, admin, app, angemeldet):  # noqa: F811
    with app.app_context():
        korrektur = storniere_rechnung(rechnung, admin.id)
    assert korrektur.belegart == "korrektur" and korrektur.nummer == "RK0001"
    assert korrektur.bezug_id == rechnung.id
    assert korrektur.summe_cent == -rechnung.summe_cent
    assert all(p.betrag_cent <= 0 for p in korrektur.positionen)
    assert rechnung.status == "storniert"
    assert rechnung not in zu_pruefen()["offen"]
    inhalt = pdf_text(angemeldet.get(f"/rechnungen/{korrektur.id}/pdf").data)
    assert "Rechnungskorrektur RK0001" in inhalt
    assert f"zu Rechnung {rechnung.nummer}" in inhalt
    assert "-152,20 €" in inhalt
    assert "nicht mehr fällig" in inhalt
    # Die Originalrechnung bleibt unverändert, auch ihr PDF
    assert "Rechnung " + rechnung.nummer in pdf_text(
        angemeldet.get(f"/rechnungen/{rechnung.id}/pdf").data
    )


def test_storno_ueber_oberflaeche(angemeldet, rechnung, session):  # noqa: F811
    antwort = angemeldet.post(f"/rechnungen/{rechnung.id}/stornieren")
    korrektur = session.execute(
        select(Rechnung).where(Rechnung.belegart == "korrektur")
    ).scalar_one()
    assert antwort.headers["Location"].endswith(f"/rechnungen/{korrektur.id}")
    liste = angemeldet.get("/rechnungen").get_data(as_text=True)
    assert "RK0001" in liste and "Rechnungskorrektur" in liste


def test_kein_storno_nach_zahlung(rechnung, admin, app):  # noqa: F811
    erfasse_zahlung(
        rechnung,
        datum=HEUTE,
        betrag_cent=1000,
        zahlungsart="bar",
        angekommen_cent=None,
        notiz=None,
        nutzer_id=admin.id,
    )
    with app.app_context(), pytest.raises(AktionNichtMoeglich, match="Geld eingegangen"):
        storniere_rechnung(rechnung, admin.id)


def test_kein_doppelstorno(rechnung, admin, app):  # noqa: F811
    with app.app_context():
        storniere_rechnung(rechnung, admin.id)
        with pytest.raises(AktionNichtMoeglich, match="bereits storniert"):
            storniere_rechnung(rechnung, admin.id)


def test_korrektur_braucht_bezug(admin, session):
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO rechnung (belegart, status, rechnungsdatum, leistung_art, titel, "
                "zahlungsziel_tage, qr_ueberweisung, summe_cent) "
                "VALUES ('korrektur', 'entwurf', CURRENT_DATE, 'leistungsdatum', 'X', 0, false, 0)"
            )
        )


def test_suche_offen_nur_rechnungen(rechnung, angebot, admin, app):  # noqa: F811
    with app.app_context():
        storniere_rechnung(rechnung, admin.id)
    assert suche_rechnungen("offen") == []
    assert suche_rechnungen("offen", angebote=True) == [angebot]


@pytest.mark.parametrize("rolle", ["mitarbeiter", "steuerberater"])
def test_rechte_storno_und_angebot(client, rechnung, session, rolle):  # noqa: F811
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/abmelden")
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.post(f"/rechnungen/{rechnung.id}/stornieren").status_code == 403
    erwartet = 302 if rolle == "mitarbeiter" else 403
    assert client.post("/angebote/neu").status_code == erwartet


def test_dashboard_splitknopf_und_zaehler(angemeldet, angebot):
    seite = angemeldet.get("/").get_data(as_text=True)
    assert "Neues Angebot" in seite
    assert "1 offenes Angebot" in seite


def test_angebot_spricht_nicht_von_rechnung(angemeldet, angebot, admin):
    """Gefunden beim Durchspielen: Datum und Hilfetexte nannten Angebote „Rechnung“."""
    seite = angemeldet.get(f"/rechnungen/{angebot.id}").get_data(as_text=True)
    assert "<dt>Angebotsdatum</dt>" in seite and "<dt>Rechnungsdatum</dt>" not in seite
    entwurf = neuer_entwurf(admin.id, "angebot")
    text = angemeldet.get(f"/rechnungen/{entwurf.id}/bearbeiten").get_data(as_text=True)
    assert "Wer das Angebot oder die Rechnung bekommt" in text
    assert "Wer die Rechnung bekommt" not in text
