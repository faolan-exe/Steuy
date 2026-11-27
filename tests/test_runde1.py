"""Fehler aus dem Praxistest vom 27.11.2026 (als Fotograf mit typischen Fehlern)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.domain.belegerkennung import aus_text
from app.domain.zahlung import ZahlungUngueltig
from app.models import Anlagegut, Buchung, Mahnung
from app.services import wiederkehrend
from app.services.buchungen import Buchungsdaten, erfasse_gebuehren, festschreiben, lege_entwurf_an
from app.services.zahlungen import erfasse_zahlung, storniere_zahlung
from tests.conftest import ADMIN_EMAIL
from tests.test_rechnungen import auftritt, bank, formular, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()


# ---------- Passwort vergessen ----------


def test_passwort_auf_dem_server_neu_setzen(app, admin, session):
    from app.domain.passwort import pruefe_passwort

    lauf = app.test_cli_runner().invoke(
        args=["passwort-setzen", ADMIN_EMAIL.upper()],
        input="ein-ganz-neues-passwort\nein-ganz-neues-passwort\n",
    )
    assert lauf.exit_code == 0, lauf.output
    session.refresh(admin)
    assert pruefe_passwort(admin.passwort_hash, "ein-ganz-neues-passwort")
    lauf = app.test_cli_runner().invoke(args=["passwort-setzen", "gibt-es@nicht.example"])
    assert lauf.exit_code != 0 and "Kein Konto" in lauf.output


def test_anmeldeseite_erklaert_passwort_vergessen(client, admin):
    seite = client.get("/anmelden").get_data(as_text=True)
    assert "Passwort vergessen" in seite


# ---------- Zahlungen und Gebühren ----------


def test_rueckgaengig_mit_gebuchter_gebuehr_wird_verhindert(rechnung, admin, session):  # noqa: F811
    zahlung = erfasse_zahlung(
        rechnung,
        datum=HEUTE,
        betrag_cent=15220,
        zahlungsart="paypal",
        angekommen_cent=14750,
        notiz=None,
        nutzer_id=admin.id,
    )
    erfasse_gebuehren([zahlung.id], admin.id)
    with pytest.raises(ZahlungUngueltig, match="Gebühr"):
        storniere_zahlung(zahlung, admin.id)


# ---------- Belege ----------


@pytest.mark.parametrize(
    ("text", "art"),
    [
        ("Summe 49,90\nBezahlt mit EC-Karte", "karte"),
        ("girocard kontaktlos 12,00", "karte"),
        ("SUMME EUR 102,45\nBar bezahlt", "bar"),
        ("Gegeben 20,00 Rückgeld 7,55", "bar"),
        ("Der Betrag wird per Lastschrift eingezogen", None),
        ("Bitte überweisen Sie bis zum 01.12.", None),
    ],
)
def test_zahlungsart_auf_dem_bon_erkannt(text, art):
    assert aus_text(text).zahlungsart == art


# ---------- Anlagegüter ----------


def test_anlagegut_ohne_vorauswahl(angemeldet, admin, session):
    from app.models import Kategorie

    kategorie = session.scalars(select(Kategorie).where(Kategorie.name.like("Geringwertig%"))).one()
    buchung = lege_entwurf_an(
        Buchungsdaten(
            art="ausgabe",
            belegdatum=HEUTE,
            betrag_cent=149900,
            kategorie_id=kategorie.id,
            betrieblich_prozent=100,
            kontakt_id=None,
            partner="Foto Koch",
            belegnummer=None,
            beschreibung="Kamera",
            beleg_id=None,
        ),
        admin.id,
    )
    festschreiben(buchung, admin.id, bezahlt_am=HEUTE, zahlungsart="karte")
    seite = angemeldet.get(f"/buchungen/{buchung.id}/anlagegut").get_data(as_text=True)
    assert 'value="computer" checked' not in seite
    # Ohne Auswahl wird nichts angelegt
    antwort = angemeldet.post(
        f"/buchungen/{buchung.id}/anlagegut",
        data={"bezeichnung": "Kamera", "anschaffungsdatum": HEUTE.isoformat()},
    )
    assert antwort.status_code == 422
    assert session.scalars(select(Anlagegut)).first() is None
    # Und „Zu prüfen“ erinnert an die fehlende Abschreibung
    assert "Kamera" in angemeldet.get("/zu-pruefen").get_data(as_text=True)


# ---------- Wiederkehrende Rechnungen ----------


def test_wiederkehrend_machen_legt_pausiert_an(angemeldet, rechnung, session):  # noqa: F811
    antwort = angemeldet.post(f"/wiederkehrend/aus-rechnung/{rechnung.id}")
    assert antwort.status_code == 302
    vorlage = session.scalars(select(wiederkehrend.WiederkehrendeRechnung)).one()
    assert vorlage.aktiv is False
    seite = angemeldet.get(antwort.headers["Location"]).get_data(as_text=True)
    assert 'name="aktiv" value="y" checked' in seite


def test_wiederkehrend_eingaben_bleiben_nach_fehler(angemeldet, admin, kunde, bank, session):  # noqa: F811
    from tests.test_wiederkehrend import vorlage_formular

    v = wiederkehrend.lege_leer_an(admin.id, heute=date(2026, 11, 1))
    daten = vorlage_formular(kunde, name="Social Media Paket", ende_am="2026-10-01")
    antwort = angemeldet.post(f"/wiederkehrend/{v.id}", data=daten)
    seite = antwort.get_data(as_text=True)
    assert antwort.status_code == 422
    assert 'value="Social Media Paket"' in seite and 'value="2026-10-01"' in seite


# ---------- Entwürfe ----------


def test_leere_positionen_fallen_beim_speichern_weg(angemeldet, admin, kunde, bank, session):  # noqa: F811
    from app.services.rechnungen import neuer_entwurf

    entwurf = neuer_entwurf(admin.id)
    daten = formular(entwurf, kunde)
    daten.update(
        {"pos-1-typ": "artikel", "pos-1-bezeichnung": "", "pos-1-menge": "1", "pos-1-preis": "0,00"}
    )
    angemeldet.post(f"/rechnungen/{entwurf.id}/bearbeiten", data=daten)
    session.refresh(entwurf)
    assert all(p.bezeichnung for p in entwurf.positionen if p.typ == "artikel")


def test_zweites_fenster_ueberschreibt_nicht_still(angemeldet, admin, kunde, bank, session):  # noqa: F811
    from app.services.rechnungen import neuer_entwurf

    entwurf = neuer_entwurf(admin.id)
    speichern(angemeldet, entwurf, kunde)
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/bearbeiten").get_data(as_text=True)
    stand = seite.split('name="stand" value="')[1].split('"')[0]
    fenster_a = formular(entwurf, kunde) | {"stand": stand, "pos-0-preis": "95,00"}
    fenster_b = formular(entwurf, kunde) | {"stand": stand, "einleitung": "Danke!"}
    assert (
        angemeldet.post(f"/rechnungen/{entwurf.id}/bearbeiten", data=fenster_a).status_code == 302
    )
    antwort = angemeldet.post(f"/rechnungen/{entwurf.id}/bearbeiten", data=fenster_b)
    assert antwort.status_code == 409
    assert "anderen Fenster" in antwort.get_data(as_text=True)
    session.refresh(entwurf)
    assert entwurf.positionen[0].einzelpreis_cent == 9500


def test_anschrift_einer_person_mit_anrede(admin, session):
    from app.services.kontakte import lege_kontakt_an

    k = lege_kontakt_an(
        {
            "art": "person",
            "anrede": "Herr Dr.",
            "vorname": "Max",
            "nachname": "Mustermann",
            "typ": "kunde",
            "strasse": "Lindenallee 7",
            "plz": "50968",
            "ort": "Köln",
        },
        admin.id,
    )
    assert k.briefname == "Herr Dr. Max Mustermann"
    assert k.name == "Mustermann, Max"


# ---------- Suche ----------


def test_suche_findet_betrag_ohne_komma_und_kurze_nummer(angemeldet, rechnung):  # noqa: F811
    from app.services.suche import _betrag

    assert _betrag("1200") == 120000 and _betrag("2026") is None
    # „152“ ohne Cent findet 152,20 €
    for text in ("152,2", "152", f"RE{int(rechnung.nummer[2:])}"):
        seite = angemeldet.get(f"/suche?q={text}").get_data(as_text=True)
        assert rechnung.nummer in seite, text


# ---------- Mahnungen ----------


def test_pauschale_warnung_auch_ohne_kontakt(angemeldet, admin, kunde, bank, app, session):  # noqa: F811
    """Eingetippter Kunde ohne Kontakt: steuy weiß nicht, ob es ein Verbraucher ist."""
    from app.services.mahnwesen import erstelle_mahnung
    from app.services.rechnungen import finalisiere, neuer_entwurf

    entwurf = neuer_entwurf(admin.id)
    # Ein Name, den es als Kontakt nicht gibt (sonst verbindet steuy ihn mit dem Kontakt)
    speichern(
        angemeldet,
        entwurf,
        kunde,
        kontakt_id="",
        empfaenger_name="Familie Neumann",
        rechnungsdatum=HEUTE.isoformat(),
    )
    with app.app_context():
        r = finalisiere(entwurf, admin.id)
        erstelle_mahnung(r, admin.id, heute=HEUTE + timedelta(days=21))
    seite = angemeldet.get(f"/rechnungen/{r.id}/mahnungen/neu").get_data(as_text=True)
    assert "Ist er Privatkunde" in seite or "kein Kontakt" in seite


def test_portal_nennt_mahnbetrag_mit_pauschale(app, rechnung, admin, session):  # noqa: F811
    from app.services import kundenportal
    from app.services.mahnwesen import erstelle_mahnung

    with app.app_context():
        erstelle_mahnung(rechnung, admin.id, heute=HEUTE + timedelta(days=21))
        erstelle_mahnung(rechnung, admin.id, heute=HEUTE + timedelta(days=35), pauschale=True)
    assert kundenportal.zu_zahlen_cent(rechnung) == rechnung.offen_cent + 4000


# ---------- Hilfe ----------


def test_keine_dateipfade_der_doku_in_der_oberflaeche():
    from pathlib import Path

    vorlagen = Path(__file__).parent.parent / "app" / "web" / "templates"
    for datei in vorlagen.rglob("*.html"):
        assert "docs/" not in datei.read_text(encoding="utf-8"), datei.name


def test_hilfe_link_im_menue(angemeldet):
    assert "faolan-exe.github.io/Steuy" in angemeldet.get("/").get_data(as_text=True)


def test_zu_pruefen_meldet_gescheiterten_automatischen_versand(
    angemeldet,
    rechnung,  # noqa: F811
    admin,
    app,
    session,  # noqa: F811
):
    from app.models import Versand

    with app.app_context():
        from app.services.mahnwesen import erstelle_mahnung

        m = erstelle_mahnung(rechnung, admin.id, heute=HEUTE + timedelta(days=21), automatisch=True)
    session.add(
        Versand(
            rechnung_id=rechnung.id,
            mahnung_id=m.id,
            an="x@y.example",
            betreff="b",
            text="t",
            anhang="a.pdf",
            erfolgreich=False,
            fehler="Mailserver nicht erreichbar",
            gesendet_von=admin.id,
        )
    )
    session.commit()
    assert "nicht verschickt" in angemeldet.get("/zu-pruefen").get_data(as_text=True)


_ = (Buchung, Mahnung)


# ---------- Fortsetzung Runde 1 ----------


def test_formular_laeuft_nicht_nach_einer_stunde_ab(app):
    """Abmeldung erst nach 8 Stunden Leerlauf, also darf das Formular nicht vorher ablaufen."""
    assert app.config.get("WTF_CSRF_TIME_LIMIT") is None


def test_mahnung_zu_stornierter_rechnung_nicht_mehr_senden(
    angemeldet,
    rechnung,  # noqa: F811
    admin,
    app,
    session,
):
    from app.services.mahnwesen import erstelle_mahnung
    from app.services.rechnungen import storniere_rechnung

    with app.app_context():
        m = erstelle_mahnung(rechnung, admin.id, heute=HEUTE + timedelta(days=21))
        storniere_rechnung(rechnung, admin.id)
    antwort = angemeldet.get(
        f"/rechnungen/{rechnung.id}/mahnungen/{m.id}/senden", follow_redirects=True
    )
    assert "storniert" in antwort.get_data(as_text=True)
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}/mahnungen/{m.id}").get_data(as_text=True)
    assert f"mahnungen/{m.id}/senden" not in seite


def test_abgelehntes_angebot_wieder_oeffnen(angemeldet, admin, kunde, bank, app, session):  # noqa: F811
    from app.services.rechnungen import entscheide_angebot, finalisiere, neuer_entwurf

    entwurf = neuer_entwurf(admin.id, "angebot")
    speichern(angemeldet, entwurf, kunde)
    with app.app_context():
        angebot = finalisiere(entwurf, admin.id)
        entscheide_angebot(angebot, False, admin.id)
    antwort = angemeldet.post(f"/rechnungen/{angebot.id}/offen")
    assert antwort.status_code == 302
    session.refresh(angebot)
    assert angebot.status == "offen"


def test_gesamtexport_enthaelt_anlagen_und_jahreszuordnung():
    from app.services.export import TABELLEN

    for tabelle in ("anlagegut", "jahreszuordnung", "versand", "wiederkehrende_rechnung"):
        assert tabelle in TABELLEN, tabelle


def test_zahlenfelder_melden_fehler_auf_deutsch(angemeldet):
    antwort = angemeldet.post(
        "/buchungen/neu",
        data={
            "art": "ausgabe",
            "betrag": "10",
            "belegdatum": HEUTE.isoformat(),
            "betrieblich_prozent": "fünfzig",
        },
    )
    seite = antwort.get_data(as_text=True)
    assert "Not a valid" not in seite and "This field" not in seite
