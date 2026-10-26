from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import Protokoll, Rechnung, Versand, WiederkehrendeRechnung
from app.services import wiederkehrend
from app.services.wiederkehrend import Einstellungen, VorlageUngueltig
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_rechnungen import auftritt, bank, formular, kunde  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401


def vorlage_formular(kunde, **mehr):  # noqa: F811
    daten = formular(None, kunde)
    daten.update(
        {
            "name": "Wartung",
            "intervall": "monatlich",
            "naechste_am": "2026-11-01",
            "versand": "entwurf",
            "aktiv": "y",
            "titel": "Wartung {monat}",
            "einleitung": "Leistungen im Zeitraum {zeitraum}.",
            "pos-0-bezeichnung": "Wartungsvertrag {monat}",
            "pos-0-menge": "1",
            "pos-0-preis": "50,00",
            "pos-1-typ": None,
            "pos-1-bezeichnung": None,
            "pos-2-typ": None,
            "pos-2-bezeichnung": None,
            "pos-2-menge": None,
            "pos-2-einheit": None,
            "pos-2-preis": None,
            "pos-2-rabatt": None,
        }
    )
    daten.update(mehr)
    return {k: v for k, v in daten.items() if v is not None}


@pytest.fixture
def vorlage(angemeldet, admin, kunde, bank, session):  # noqa: F811
    """Wartung für 50 € im Monat, ab 1.11.2026, nur Entwurf."""
    v = wiederkehrend.lege_leer_an(admin.id, heute=date(2026, 11, 1))
    antwort = angemeldet.post(f"/wiederkehrend/{v.id}", data=vorlage_formular(kunde))
    assert antwort.status_code == 302, antwort.get_data(as_text=True)[:500]
    session.refresh(v)
    return v


def rechnungen_zu(session, v):
    return list(
        session.scalars(
            select(Rechnung).where(Rechnung.wiederkehrend_id == v.id).order_by(Rechnung.id)
        )
    )


# ---------- Vorlage speichern ----------


def test_vorlage_wird_mit_positionen_und_summe_gespeichert(vorlage):
    assert vorlage.name == "Wartung" and vorlage.intervall == "monatlich"
    assert vorlage.naechste_am == date(2026, 11, 1) and vorlage.anker_tag == 1
    assert vorlage.summe_cent == 5000 and len(vorlage.positionen) == 1
    assert vorlage.empfaenger_name == "Café Sonnenschein" and vorlage.kontakt_id


@pytest.mark.parametrize(
    "aenderung",
    [
        {"name": " "},
        {"intervall": "woechentlich"},
        {"naechste_am": ""},
        {"naechste_am": "kein-datum"},
        {"ende_am": "2026-10-01"},
        {"versand": "irgendwas"},
        {"pos-0-preis": "abc"},
    ],
)
def test_ungueltige_eingaben_speichern_nichts(angemeldet, vorlage, kunde, aenderung):  # noqa: F811
    antwort = angemeldet.post(
        f"/wiederkehrend/{vorlage.id}", data=vorlage_formular(kunde, **aenderung)
    )
    assert antwort.status_code == 422
    assert vorlage.name == "Wartung" and vorlage.naechste_am == date(2026, 11, 1)


def test_neuer_starttermin_setzt_den_ankertag(angemeldet, vorlage, kunde, session):  # noqa: F811
    angemeldet.post(
        f"/wiederkehrend/{vorlage.id}", data=vorlage_formular(kunde, naechste_am="2026-11-15")
    )
    session.refresh(vorlage)
    assert vorlage.anker_tag == 15


# ---------- Erzeugen ----------


def test_faellige_vorlage_erzeugt_entwurf_mit_zeitraum_und_platzhaltern(
    vorlage, admin, session, app
):
    with app.app_context():
        lauf = wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
    assert len(lauf.erstellt) == 1 and not lauf.probleme
    (r,) = rechnungen_zu(session, vorlage)
    assert r.status == "entwurf" and r.nummer is None
    assert r.rechnungsdatum == date(2026, 11, 1)
    assert (r.leistung_art, r.leistung_von, r.leistung_bis) == (
        "leistungszeitraum",
        date(2026, 11, 1),
        date(2026, 11, 30),
    )
    assert r.titel == "Wartung November 2026"
    assert r.einleitung == "Leistungen im Zeitraum 01.11.2026 bis 30.11.2026."
    assert r.positionen[0].bezeichnung == "Wartungsvertrag November 2026"
    assert r.summe_cent == 5000 and r.kontakt_id == vorlage.kontakt_id
    session.refresh(vorlage)
    assert vorlage.naechste_am == date(2026, 12, 1) and vorlage.erzeugt_anzahl == 1
    assert vorlage.letzter_lauf_am is not None


def test_noch_nicht_faellig_oder_pausiert_erzeugt_nichts(vorlage, admin, session, app):
    with app.app_context():
        assert wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 10, 31)).leer
        wiederkehrend.setze_aktiv(vorlage, False, admin.id)
        assert wiederkehrend.fuehre_aus(admin.id, heute=date(2027, 3, 1)).leer
    assert rechnungen_zu(session, vorlage) == []


def test_zweiter_lauf_am_selben_tag_erzeugt_nichts_doppelt(vorlage, admin, session, app):
    with app.app_context():
        wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
        wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
        wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 20))
    assert len(rechnungen_zu(session, vorlage)) == 1


def test_verpasste_termine_werden_nachgeholt(vorlage, admin, session, app):
    with app.app_context():
        lauf = wiederkehrend.fuehre_aus(admin.id, heute=date(2027, 1, 10))
    assert len(lauf.erstellt) == 3  # 1.11., 1.12., 1.1.
    zeitraeume = [(r.leistung_von, r.leistung_bis) for r in rechnungen_zu(session, vorlage)]
    assert zeitraeume == [
        (date(2026, 11, 1), date(2026, 11, 30)),
        (date(2026, 12, 1), date(2026, 12, 31)),
        (date(2027, 1, 1), date(2027, 1, 31)),
    ]
    assert {r.rechnungsdatum for r in rechnungen_zu(session, vorlage)} == {date(2027, 1, 10)}


def test_ende_wird_beachtet(angemeldet, vorlage, kunde, admin, session, app):  # noqa: F811
    angemeldet.post(
        f"/wiederkehrend/{vorlage.id}", data=vorlage_formular(kunde, ende_am="2026-12-15")
    )
    with app.app_context():
        wiederkehrend.fuehre_aus(admin.id, heute=date(2027, 6, 1))
    assert len(rechnungen_zu(session, vorlage)) == 2
    session.refresh(vorlage)
    assert vorlage.beendet


def test_quartal_mit_monatsende_anker(angemeldet, admin, kunde, bank, session, app):  # noqa: F811
    v = wiederkehrend.lege_leer_an(admin.id, heute=date(2026, 1, 31))
    angemeldet.post(
        f"/wiederkehrend/{v.id}",
        data=vorlage_formular(kunde, intervall="monatlich", naechste_am="2026-01-31"),
    )
    with app.app_context():
        wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 3, 31))
    r = rechnungen_zu(session, v)
    assert [(x.leistung_von, x.leistung_bis) for x in r] == [
        (date(2026, 1, 31), date(2026, 2, 27)),
        (date(2026, 2, 28), date(2026, 3, 30)),
        (date(2026, 3, 31), date(2026, 4, 29)),
    ]


# ---------- Festschreiben und Versand ----------


def test_festschreiben_vergibt_nummer_und_pdf(angemeldet, vorlage, kunde, admin, session, app):  # noqa: F811
    angemeldet.post(
        f"/wiederkehrend/{vorlage.id}", data=vorlage_formular(kunde, versand="festschreiben")
    )
    with app.app_context():
        lauf = wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
    (r,) = rechnungen_zu(session, vorlage)
    assert r.status == "offen" and r.nummer and r.pdf_sha256 and r.faellig_am == date(2026, 11, 15)
    assert lauf.festgeschrieben == [r.nummer] and not lauf.versendet


def test_senden_verschickt_pdf_per_mail(angemeldet, vorlage, kunde, admin, session, app):  # noqa: F811
    from app.models import Gewerbe, Kontakt

    gewerbe = session.get(Gewerbe, 1)
    gewerbe.smtp_server, gewerbe.mail_absender = "smtp.test.example", "rechnung@test.example"
    session.get(Kontakt, vorlage.kontakt_id).email = "kunde@test.example"
    session.commit()
    angemeldet.post(f"/wiederkehrend/{vorlage.id}", data=vorlage_formular(kunde, versand="senden"))
    with app.app_context():
        lauf = wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
        ausgang = app.extensions["mail_ausgang"]
    (r,) = rechnungen_zu(session, vorlage)
    assert lauf.versendet == [r.nummer] and not lauf.probleme
    assert ausgang[-1]["To"] == "kunde@test.example" and r.nummer in ausgang[-1]["Subject"]
    assert session.scalar(select(func.count()).select_from(Versand)) == 1


def test_senden_ohne_mail_einrichtung_laesst_festgeschriebene_rechnung_stehen(
    angemeldet,
    vorlage,
    kunde,  # noqa: F811
    admin,
    session,
    app,
):
    angemeldet.post(f"/wiederkehrend/{vorlage.id}", data=vorlage_formular(kunde, versand="senden"))
    with app.app_context():
        lauf = wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
    (r,) = rechnungen_zu(session, vorlage)
    assert r.status == "offen" and r.nummer and not lauf.versendet
    assert "nicht eingerichtet" in lauf.probleme[0][1]
    session.refresh(vorlage)
    assert "nicht eingerichtet" in vorlage.letzte_meldung


def test_festschreiben_mit_fehlenden_angaben_bleibt_entwurf(angemeldet, admin, bank, session, app):  # noqa: F811
    v = wiederkehrend.lege_leer_an(admin.id, heute=date(2026, 11, 1))
    v.versand, v.name = "festschreiben", "Ohne Kunde"
    session.commit()
    with app.app_context():
        lauf = wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
    (r,) = rechnungen_zu(session, v)
    assert r.status == "entwurf" and r.nummer is None
    assert "Angaben fehlen" in lauf.probleme[0][1]


# ---------- Jetzt anlegen, Löschen, Aus Rechnung ----------


def test_jetzt_anlegen_erzeugt_entwurf_und_setzt_termin_weiter(angemeldet, vorlage, session):
    antwort = angemeldet.post(f"/wiederkehrend/{vorlage.id}/jetzt")
    assert antwort.status_code == 302 and "/bearbeiten" in antwort.headers["Location"]
    session.refresh(vorlage)
    assert vorlage.naechste_am == date(2026, 12, 1) and vorlage.erzeugt_anzahl == 1
    assert len(rechnungen_zu(session, vorlage)) == 1


def test_vorlage_mit_rechnungen_laesst_sich_nicht_loeschen(angemeldet, vorlage, session):
    angemeldet.post(f"/wiederkehrend/{vorlage.id}/jetzt")
    antwort = angemeldet.post(f"/wiederkehrend/{vorlage.id}/loeschen", follow_redirects=True)
    assert "nur pausieren" in antwort.get_data(as_text=True)
    assert session.get(WiederkehrendeRechnung, vorlage.id) is not None


def test_vorlage_ohne_rechnungen_laesst_sich_loeschen(angemeldet, vorlage, session):
    angemeldet.post(f"/wiederkehrend/{vorlage.id}/loeschen")
    assert session.scalar(select(func.count()).select_from(WiederkehrendeRechnung)) == 0


def test_finalisierte_rechnung_wird_zur_vorlage(angemeldet, rechnung, session):  # noqa: F811
    antwort = angemeldet.post(f"/wiederkehrend/aus-rechnung/{rechnung.id}")
    assert antwort.status_code == 302
    (v,) = session.scalars(select(WiederkehrendeRechnung)).all()
    assert v.summe_cent == rechnung.summe_cent and len(v.positionen) == len(rechnung.positionen)
    assert v.empfaenger_name == rechnung.empfaenger_name and v.versand == "entwurf"
    assert v.anker_tag == rechnung.rechnungsdatum.day
    assert v.naechste_am > rechnung.rechnungsdatum


def test_entwurf_kann_nicht_zur_vorlage_werden(angemeldet, admin, kunde, bank, session):  # noqa: F811
    from app.services.rechnungen import neuer_entwurf

    entwurf = neuer_entwurf(admin.id, "angebot")
    with pytest.raises(VorlageUngueltig):
        wiederkehrend.lege_aus_rechnung_an(entwurf, admin.id)


def test_einstellungen_pruefen():
    ok = Einstellungen("A", "monatlich", date(2026, 1, 1), None, "entwurf", True)
    wiederkehrend.pruefe_einstellungen(ok)
    for aenderung in (
        {"name": ""},
        {"intervall": "x"},
        {"versand": "x"},
        {"ende_am": date(2025, 1, 1)},
    ):
        with pytest.raises(VorlageUngueltig):
            wiederkehrend.pruefe_einstellungen(Einstellungen(**{**ok.__dict__, **aenderung}))


# ---------- Seiten und Rechte ----------


def test_seiten_laden(angemeldet, vorlage, session):
    liste = angemeldet.get("/wiederkehrend").get_data(as_text=True)
    assert "Wartung" in liste and "01.11.2026" in liste and "Jeden Monat" in liste
    editor = angemeldet.get(f"/wiederkehrend/{vorlage.id}").get_data(as_text=True)
    assert "Wartungsvertrag {monat}" in editor and "Wie oft" in editor
    assert "{zeitraum}" in editor  # Hinweis auf die Platzhalter


def test_rechnungsliste_und_detail_verlinken_die_funktion(angemeldet, rechnung):  # noqa: F811
    assert "/wiederkehrend" in angemeldet.get("/rechnungen").get_data(as_text=True)
    html = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert "Wiederkehrend machen" in html


def test_manueller_lauf_ueber_die_seite(angemeldet, vorlage, session, monkeypatch):
    import app.services.wiederkehrend as dienst

    echt = dienst.date
    heute = date(2026, 11, 3)

    class FesterTag(date):
        @classmethod
        def today(cls):
            return heute

    monkeypatch.setattr(dienst, "date", FesterTag)
    antwort = angemeldet.post("/wiederkehrend/lauf", follow_redirects=True)
    monkeypatch.setattr(dienst, "date", echt)
    assert "1 Rechnung(en) angelegt" in antwort.get_data(as_text=True)


def test_befehl_wiederkehrend_lauf(app, vorlage, session):
    ergebnis = app.test_cli_runner().invoke(args=["wiederkehrend-lauf"])
    assert ergebnis.exit_code == 0
    assert "angelegt" in ergebnis.output or "Keine Rechnung fällig" in ergebnis.output


@pytest.mark.parametrize(
    ("rolle", "ansehen", "aendern"),
    [("steuerberater", 200, 403), ("mitarbeiter", 200, 200), ("buchhalter", 200, 200)],
)
def test_rechte(app, admin, vorlage, session, rolle, ansehen, aendern):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client = app.test_client()  # eigener Browser, der angemeldete Admin bleibt außen vor
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/wiederkehrend").status_code == ansehen
    assert client.get(f"/wiederkehrend/{vorlage.id}").status_code == ansehen
    erwartet = 302 if aendern == 200 else 403
    assert client.post(f"/wiederkehrend/{vorlage.id}/pausieren").status_code == erwartet
    assert client.post("/wiederkehrend/neu").status_code == erwartet
    assert client.post(f"/wiederkehrend/{vorlage.id}/jetzt").status_code == erwartet
    assert client.post("/wiederkehrend/lauf").status_code == erwartet
    # Nur lesende Rollen dürfen die Vorlage nicht per Formular ändern
    assert client.post(f"/wiederkehrend/{vorlage.id}", data={"name": "x"}).status_code in (
        403,
        422,
    )


def test_ohne_anmeldung_gesperrt(client, admin):
    assert client.get("/wiederkehrend").status_code == 302
    assert client.post("/wiederkehrend/lauf").status_code == 302


def test_protokoll_nennt_vorlage_und_erzeugte_rechnung(vorlage, admin, session, app):
    with app.app_context():
        wiederkehrend.fuehre_aus(admin.id, heute=date(2026, 11, 1))
    aktionen = set(session.scalars(select(Protokoll.aktion)))
    assert {
        "wiederkehrend_angelegt",
        "wiederkehrend_geaendert",
        "wiederkehrend_rechnung_erzeugt",
    } <= aktionen
