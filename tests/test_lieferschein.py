# ruff: noqa: F811
import io
from datetime import date

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.models import Rechnung
from app.services.rechnungen import (
    AktionNichtMoeglich,
    belegkette,
    lieferschein_aus_rechnung,
    lieferscheine_zu,
    storniere_rechnung,
)
from tests.test_angebote import angebot  # noqa: F401
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401


def pdf_text(inhalt: bytes) -> str:
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(inhalt)).pages)


def test_lieferschein_aus_rechnung(angemeldet, rechnung, session):  # noqa: F811
    antwort = angemeldet.post(f"/rechnungen/{rechnung.id}/lieferschein")
    assert antwort.status_code == 302
    ls = session.execute(select(Rechnung).where(Rechnung.belegart == "lieferschein")).scalar_one()
    assert ls.nummer == "LS0001" and ls.bezug_id == rechnung.id
    assert ls.status == "offen" and ls.summe_cent == 0 and ls.offen_cent == 0
    assert [p.bezeichnung for p in ls.positionen] == [p.bezeichnung for p in rechnung.positionen]
    assert all(p.einzelpreis_cent == 0 and p.betrag_cent == 0 for p in ls.positionen)
    text = pdf_text(angemeldet.get(f"/rechnungen/{ls.id}/pdf").data)
    assert "Lieferschein LS0001" in text and "Auftritt" in text
    assert "Einzelpreis" not in text and "Gesamtbetrag" not in text and "IBAN" not in text
    assert f"Rechnung {rechnung.nummer}" in text


def test_nur_ein_lieferschein_je_rechnung(angemeldet, rechnung, admin, app, session):  # noqa: F811
    angemeldet.post(f"/rechnungen/{rechnung.id}/lieferschein")
    antwort = angemeldet.post(f"/rechnungen/{rechnung.id}/lieferschein", follow_redirects=True)
    assert "schon einen Lieferschein" in antwort.get_data(as_text=True)
    assert len(lieferscheine_zu(rechnung)) == 1
    with app.app_context(), pytest.raises(AktionNichtMoeglich):
        lieferschein_aus_rechnung(rechnung, admin.id)


def test_kein_lieferschein_zu_storniertem_oder_entwurf(angemeldet, rechnung, admin, app, session):  # noqa: F811
    with app.app_context():
        storniere_rechnung(rechnung, admin.id)
        with pytest.raises(AktionNichtMoeglich):
            lieferschein_aus_rechnung(rechnung, admin.id)
    assert (
        session.execute(select(Rechnung).where(Rechnung.belegart == "lieferschein")).first() is None
    )


def test_lieferschein_nicht_in_rechnungsliste_und_nicht_offen(angemeldet, rechnung, session):  # noqa: F811
    angemeldet.post(f"/rechnungen/{rechnung.id}/lieferschein")
    ls = session.execute(select(Rechnung).where(Rechnung.belegart == "lieferschein")).scalar_one()
    liste = angemeldet.get("/rechnungen").get_data(as_text=True)
    assert f'href="/rechnungen/{ls.id}"' not in liste
    assert f'href="/rechnungen/{ls.id}"' not in angemeldet.get("/zu-pruefen").get_data(as_text=True)


def test_lieferschein_detailseite_und_verlinkung(angemeldet, rechnung, session):  # noqa: F811
    angemeldet.post(f"/rechnungen/{rechnung.id}/lieferschein")
    ls = session.execute(select(Rechnung).where(Rechnung.belegart == "lieferschein")).scalar_one()
    seite = angemeldet.get(f"/rechnungen/{ls.id}").get_data(as_text=True)
    assert "Lieferschein LS0001" in seite and "Zu Rechnung" in seite
    assert "Gesamtbetrag" not in seite and "Zahlung erfassen" not in seite
    assert f'href="/rechnungen/{rechnung.id}"' in seite
    rechnung_seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert f'href="/rechnungen/{ls.id}"' in rechnung_seite
    assert "Zusammengehörige Belege" in rechnung_seite


def test_belegkette_angebot_rechnung_lieferschein_mahnung(angemeldet, angebot, kunde, session):  # noqa: F811
    angemeldet.post(f"/rechnungen/{angebot.id}/in-rechnung")
    rechnung_neu = session.execute(
        select(Rechnung).where(Rechnung.belegart == "rechnung")
    ).scalar_one()
    heute = date.today().isoformat()
    speichern(angemeldet, rechnung_neu, kunde, rechnungsdatum=heute, leistung_von=heute)
    angemeldet.post(f"/rechnungen/{rechnung_neu.id}/finalisieren")
    angemeldet.post(f"/rechnungen/{rechnung_neu.id}/lieferschein")
    angemeldet.post(f"/rechnungen/{rechnung_neu.id}/mahnungen")
    ls = session.execute(select(Rechnung).where(Rechnung.belegart == "lieferschein")).scalar_one()
    session.refresh(rechnung_neu)
    mahnung = rechnung_neu.mahnungen[0]
    ziele = {
        "angebot": f"/rechnungen/{angebot.id}",
        "rechnung": f"/rechnungen/{rechnung_neu.id}",
        "lieferschein": f"/rechnungen/{ls.id}",
        "mahnung": f"/rechnungen/{rechnung_neu.id}/mahnungen/{mahnung.id}",
    }
    seiten = {name: pfad for name, pfad in ziele.items()}
    for name, pfad in seiten.items():
        text = angemeldet.get(pfad).get_data(as_text=True)
        assert "Zusammengehörige Belege" in text, name
        for anderer, ziel in ziele.items():
            if anderer != name:
                assert f'href="{ziel}"' in text, (name, anderer)
    kette = belegkette(angebot)
    assert [(e["tiefe"], e["mahnung"] is not None) for e in kette] == [
        (0, False),
        (1, False),
        (2, True),
        (2, False),
    ]


def test_angebot_hebt_angebote_in_der_navigation_hervor(angemeldet, angebot):  # noqa: F811
    seite = angemeldet.get(f"/rechnungen/{angebot.id}").get_data(as_text=True)
    assert 'aria-current="page">Angebote</a>' in seite
    assert 'aria-current="page">Rechnungen</a>' not in seite


def test_mahnungskarte_nur_wenn_relevant(angemeldet, rechnung, admin, app):  # noqa: F811
    from app.services.zahlungen import erfasse_zahlung

    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert 'id="mahnungen"' in seite
    with app.app_context():
        erfasse_zahlung(
            rechnung,
            datum=rechnung.rechnungsdatum,
            betrag_cent=rechnung.summe_cent,
            zahlungsart="ueberweisung",
            angekommen_cent=None,
            notiz=None,
            nutzer_id=admin.id,
        )
    bezahlt = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert 'id="mahnungen"' not in bezahlt


def test_mahnung_detailseite(angemeldet, rechnung, session):  # noqa: F811
    angemeldet.post(f"/rechnungen/{rechnung.id}/mahnungen")
    session.refresh(rechnung)
    m = rechnung.mahnungen[0]
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}/mahnungen/{m.id}").get_data(as_text=True)
    assert "Zahlungserinnerung" in seite and rechnung.nummer in seite
    assert f'href="/rechnungen/{rechnung.id}"' in seite
    assert angemeldet.get(f"/rechnungen/{rechnung.id + 99}/mahnungen/{m.id}").status_code == 404
    assert angemeldet.get(f"/rechnungen/{rechnung.id}/mahnungen/{m.id + 99}").status_code == 404


def test_angebot_nur_einmal_in_rechnung(angemeldet, angebot, session):  # noqa: F811
    angemeldet.post(f"/rechnungen/{angebot.id}/in-rechnung")
    seite = angemeldet.get(f"/rechnungen/{angebot.id}").get_data(as_text=True)
    assert "In Rechnung umwandeln" not in seite
    antwort = angemeldet.post(f"/rechnungen/{angebot.id}/in-rechnung", follow_redirects=True)
    assert "schon eine Rechnung" in antwort.get_data(as_text=True)
    assert len(session.execute(select(Rechnung).where(Rechnung.belegart == "rechnung")).all()) == 1


def test_editor_laedt_live_berechnung(angemeldet, admin):
    from app.services.rechnungen import neuer_entwurf

    entwurf = neuer_entwurf(admin.id, "angebot")
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/bearbeiten").get_data(as_text=True)
    assert "js/positionen.js" in seite and 'class="positionsbetrag"' in seite
    assert angemeldet.get("/static/js/positionen.js").status_code == 200


def test_editor_traegt_anschrift_beim_kundenwechsel_ein(angemeldet, admin, kunde, bank):  # noqa: F811
    from app.services.rechnungen import neuer_entwurf

    entwurf = neuer_entwurf(admin.id)
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/bearbeiten").get_data(as_text=True)
    assert f'data-strasse="{kunde.strasse}"' in seite and f'data-ort="{kunde.ort}"' in seite
    assert "sofort aus dem Kontakt übernommen" in seite
    js = angemeldet.get("/static/js/positionen.js").get_data(as_text=True)
    assert "kontakt_id" in js and "empfaenger_strasse" in js


def test_navigation_bleibt_bei_angeboten_im_editor_und_beim_senden(angemeldet, angebot):  # noqa: F811
    for pfad in ("bearbeiten", "vorschau", "senden"):
        seite = angemeldet.get(f"/rechnungen/{angebot.id}/{pfad}", follow_redirects=True)
        text = seite.get_data(as_text=True)
        assert 'aria-current="page">Angebote</a>' in text, pfad
        assert 'aria-current="page">Rechnungen</a>' not in text, pfad


def test_lieferschein_laesst_sich_per_mail_vorbereiten(angemeldet, rechnung, session, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.web.rechnungen.mail_eingerichtet", lambda: True)
    angemeldet.post(f"/rechnungen/{rechnung.id}/lieferschein")
    ls = session.execute(select(Rechnung).where(Rechnung.belegart == "lieferschein")).scalar_one()
    seite = angemeldet.get(f"/rechnungen/{ls.id}/senden")
    assert seite.status_code == 200
    assert f"Lieferschein {ls.nummer} von" in seite.get_data(as_text=True)


@pytest.mark.parametrize("art", ["rechnung", "angebot", "korrektur", "lieferschein", "mahnung"])
def test_jede_belegart_hat_eine_mailvorlage(art):
    from app.domain.mail import vorlage

    werte = {
        "nummer": "X1",
        "firma": "F",
        "inhaber": "I",
        "betrag": "1 €",
        "faellig": "",
        "gueltig": "",
        "bezeichnung": "B",
        "frist": "",
    }
    betreff, text = vorlage(art, werte)
    assert betreff and text


def test_stornieren_mit_zahlung_zeigt_hinweis_statt_knopf(angemeldet, rechnung, admin, app):  # noqa: F811
    from app.services.zahlungen import erfasse_zahlung

    with app.app_context():
        erfasse_zahlung(
            rechnung,
            datum=rechnung.rechnungsdatum,
            betrag_cent=1000,
            zahlungsart="bar",
            angekommen_cent=None,
            notiz=None,
            nutzer_id=admin.id,
        )
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert 'aria-disabled="true"' in seite and "Erst die Zahlung" in seite
    assert f"rechnungen/{rechnung.id}/stornieren" not in seite


def test_korrektur_zeigt_status_korrektur_und_zaehler_ohne_stornierte(
    angemeldet, rechnung, admin, app, session
):  # noqa: F811
    from app.models import Rechnung
    from app.services.rechnungen import storniere_rechnung
    from app.services.zahlungen import kennzahlen

    with app.app_context():
        assert kennzahlen(rechnung.rechnungsdatum.year)["anzahl_rechnungen"] == 1
        korrektur = storniere_rechnung(rechnung, admin.id)
        assert kennzahlen(rechnung.rechnungsdatum.year)["anzahl_rechnungen"] == 0
    seite = angemeldet.get(f"/rechnungen/{korrektur.id}").get_data(as_text=True)
    assert "<dd>Korrektur</dd>" in seite
    assert session.get(Rechnung, rechnung.id).status == "storniert"
