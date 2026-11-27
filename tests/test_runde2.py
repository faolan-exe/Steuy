"""Offene Punkte aus dem Praxistest vom 27.11.2026, zweite Runde."""

from sqlalchemy import select

from app.models import Gewerbe
from app.services.rechnungen import finalisierungsfehler, neuer_entwurf, pruefhinweise
from tests.test_angebote import angebot  # noqa: F401
from tests.test_rechnungen import auftritt, bank, entwurf, kunde, speichern  # noqa: F401

# ---------- Steuernummer ist Pflichtangabe (§ 34a Nr. 2 UStDV) ----------


def test_ohne_steuernummer_kein_finalisieren(angemeldet, entwurf, session):  # noqa: F811
    gewerbe = session.get(Gewerbe, 1)
    gewerbe.steuernummer = None
    gewerbe.ust_idnr = None
    session.commit()
    fehler = finalisierungsfehler(entwurf, gewerbe, regeln=False)
    assert any("Steuernummer" in f for f in fehler)
    gewerbe.ust_idnr = "DE123456789"
    assert not any("Steuernummer" in f for f in finalisierungsfehler(entwurf, gewerbe, False))


def test_firmendaten_ohne_steuernummer_warnen(angemeldet, session):
    from tests.test_firmendaten import FIRMENDATEN

    antwort = angemeldet.post(
        "/einstellungen/firma",
        data={**FIRMENDATEN, "steuernummer": "", "ust_idnr": ""},
        follow_redirects=True,
    )
    assert "Ohne Steuernummer" in antwort.get_data(as_text=True)


# ---------- Kleinunternehmergrenze ----------


def test_hinweis_wenn_rechnung_die_grenze_ueberschreitet(angemeldet, entwurf, session):  # noqa: F811
    gewerbe = session.get(Gewerbe, 1)
    assert not any("Kleinunternehmer" in h for h in pruefhinweise(entwurf, gewerbe))
    entwurf.summe_cent = 2_600_000
    hinweise = pruefhinweise(entwurf, gewerbe)
    assert any("25.000,00 €" in h for h in hinweise), hinweise
    entwurf.summe_cent = 10_100_000
    assert any("100.000,00 €" in h for h in pruefhinweise(entwurf, gewerbe))
    session.rollback()


# ---------- Kunde im EU-Ausland ----------


def test_reverse_charge_bei_firma_im_eu_ausland(angemeldet, admin, kunde, bank, session):  # noqa: F811
    from app.domain.eu import eu_land, ist_eu_ausland

    assert eu_land("Österreich") == "AT" and eu_land("EL") == "GR" and eu_land("") == "DE"
    assert not ist_eu_ausland("Schweiz") and not ist_eu_ausland("Deutschland")

    kunde.land = "Österreich"
    session.commit()
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde, empfaenger_land="Österreich")
    session.refresh(rechnung)
    gewerbe = session.get(Gewerbe, 1)
    assert any("Reverse Charge" in h for h in pruefhinweise(rechnung, gewerbe))
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}/vorschau").get_data(as_text=True)
    assert "Steuerschuldnerschaft des Leistungsempfängers“ ergänzen" in seite

    angemeldet.post(f"/rechnungen/{rechnung.id}/reverse-charge")
    session.refresh(rechnung)
    assert rechnung.hinweis_steuerbefreiung.startswith("Steuerschuldnerschaft")
    assert "19" in rechnung.hinweis_steuerbefreiung  # Kleinunternehmer-Hinweis bleibt
    assert not any("Reverse Charge" in h for h in pruefhinweise(rechnung, gewerbe))
    assert finalisierungsfehler(rechnung, gewerbe, regeln=False) == []


def test_kein_reverse_charge_hinweis_bei_privatkunden(angemeldet, admin, bank, session):  # noqa: F811
    from app.services.kontakte import lege_kontakt_an

    privat = lege_kontakt_an(
        {
            "art": "person",
            "vorname": "Anna",
            "nachname": "Huber",
            "typ": "kunde",
            "strasse": "Ring 1",
            "plz": "1010",
            "ort": "Wien",
            "land": "Österreich",
        },
        admin.id,
    )
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, privat, empfaenger_land="Österreich")
    session.refresh(rechnung)
    assert not any("Reverse Charge" in h for h in pruefhinweise(rechnung, session.get(Gewerbe, 1)))


# ---------- Kontakte: Dubletten, eingetippte Kunden, geänderte Anschrift ----------


def test_namensschluessel():
    from app.services.kontakte import namensschluessel

    assert namensschluessel("Mustermann, Max") == namensschluessel("Herr Dr. Max  Mustermann")
    assert namensschluessel("Café Sonnenschein") == namensschluessel("café sonnenschein")
    assert namensschluessel("Max Mustermann") != namensschluessel("Maxi Mustermann")


def test_doppelter_kontakt_wird_angezeigt(angemeldet, kunde, session):  # noqa: F811
    from app.models import Kontakt

    # Gleicher Name, andere Schreibweise (doppeltes Leerzeichen)
    daten = {"art": "firma", "firmenname": "Café  Sonnenschein", "typ": "kunde"}
    daten["land"] = "Deutschland"
    antwort = angemeldet.post("/kontakte/neu", data=daten)
    assert antwort.status_code == 200
    assert "gibt es vielleicht schon" in antwort.get_data(as_text=True)
    assert len(session.execute(select(Kontakt)).all()) == 1
    antwort = angemeldet.post("/kontakte/neu", data={**daten, "doppelt_ok": "1"})
    assert antwort.status_code == 302
    assert len(session.execute(select(Kontakt)).all()) == 2


def test_eingetippter_kunde_wird_mit_kontakt_verbunden(angemeldet, admin, kunde, session):  # noqa: F811
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde, kontakt_id="", empfaenger_name="café sonnenschein")
    session.refresh(rechnung)
    assert rechnung.kontakt_id == kunde.id
    assert rechnung.empfaenger_name == "café sonnenschein"  # Eingetipptes bleibt


def test_eingetippten_kunden_als_kontakt_speichern(angemeldet, admin, kunde, session):  # noqa: F811
    rechnung = neuer_entwurf(admin.id)
    speichern(angemeldet, rechnung, kunde, kontakt_id="", empfaenger_name="Neue Kundin GmbH")
    session.refresh(rechnung)
    assert rechnung.kontakt_id is None
    vorschau = angemeldet.get(f"/rechnungen/{rechnung.id}/vorschau").get_data(as_text=True)
    assert f"/kontakte/neu?fuer={rechnung.id}" in vorschau
    seite = angemeldet.get(f"/kontakte/neu?fuer={rechnung.id}").get_data(as_text=True)
    assert 'value="Neue Kundin GmbH"' in seite and "Markt 5" in seite
    antwort = angemeldet.post(
        "/kontakte/neu",
        data={
            "fuer": rechnung.id,
            "art": "firma",
            "firmenname": "Neue Kundin GmbH",
            "typ": "kunde",
            "strasse": "Markt 5",
            "plz": "50667",
            "ort": "Köln",
            "land": "Deutschland",
        },
    )
    assert antwort.headers["Location"].endswith(f"/rechnungen/{rechnung.id}/bearbeiten")
    session.refresh(rechnung)
    assert rechnung.kontakt.name == "Neue Kundin GmbH"


def test_hinweis_wenn_kontaktanschrift_geaendert(angemeldet, entwurf, kunde, session):  # noqa: F811
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/bearbeiten").get_data(as_text=True)
    assert "Neue Anschrift übernehmen" not in seite
    kunde.strasse = "Domplatz 1"
    session.commit()
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/bearbeiten").get_data(as_text=True)
    assert "Neue Anschrift übernehmen" in seite and 'data-strasse="Domplatz 1"' in seite


# ---------- Belege: altes Datum, doppelt, eigene Rechnung ----------


def test_beleghinweise(angemeldet, admin, session):
    from datetime import date, timedelta
    from types import SimpleNamespace

    from app.services.buchungen import Buchungsdaten, beleghinweise, lege_entwurf_an

    heute = date.today()

    def hinweise(**werte):
        basis = {
            "belegdatum": heute,
            "betrag_cent": 4990,
            "partner": "Foto Meier",
            "kontakt_id": None,
            "belegnummer": None,
        }
        return beleghinweise(**{**basis, **werte})

    assert hinweise() == []
    assert "über ein Jahr alt" in hinweise(belegdatum=heute - timedelta(days=400))[0]

    lege_entwurf_an(
        Buchungsdaten(
            art="ausgabe",
            belegdatum=heute,
            betrag_cent=4990,
            kategorie_id=None,
            partner="foto meier",
        ),
        admin.id,
    )
    assert "zweimal erfasst" in hinweise()[0]
    assert hinweise(partner="Ganz Anderer Laden") == []

    eigene = SimpleNamespace(text="Steuernummer 12/345/67890", vorschlag={})
    assert "Rechnung von dir selbst" in hinweise(betrag_cent=1, beleg=eigene)[0]
    fremd = SimpleNamespace(text="Kundennr. 1234567890123", vorschlag={"lieferant": "Telekom"})
    assert hinweise(betrag_cent=1, beleg=fremd) == []


# ---------- Mailtext passt zum Stand der Rechnung ----------


def test_mailtext_bei_bezahlter_rechnung(app, angemeldet, entwurf, session):  # noqa: F811
    from app.services.versand import vorschlag

    angemeldet.post(f"/rechnungen/{entwurf.id}/finalisieren")
    session.refresh(entwurf)
    with app.test_request_context():
        assert "überweisen" in vorschlag(entwurf)["text"]
        entwurf.status = "bezahlt"
        text = vorschlag(entwurf)["text"]
    assert "bereits bezahlt" in text and "überweisen" not in text
    session.rollback()


# ---------- Angenommene Angebote ----------


def test_angenommenes_angebot_unter_zu_pruefen(angemeldet, angebot, session):  # noqa: F811
    angebot.status = "angenommen"
    session.commit()
    seite = angemeldet.get("/zu-pruefen").get_data(as_text=True)
    assert "Angenommene Angebote ohne Rechnung" in seite and angebot.nummer in seite


# ---------- Prüfungen: Leitweg-ID, Anschrift, Suche, Protokoll ----------


def test_leitweg_id():
    from app.domain.leitweg import leitweg_fehler, sieht_aus_wie_leitweg_id

    assert leitweg_fehler("04011000-1234512345-06") is None
    assert leitweg_fehler("991-33333test-33") is None
    assert "Prüfziffer" in leitweg_fehler("04011000-1234512345-07")
    assert "sieht so aus" in leitweg_fehler("04011000")
    assert sieht_aus_wie_leitweg_id("991-12") and not sieht_aus_wie_leitweg_id("Bestellung 4711")


def test_leitweg_id_im_kontakt(angemeldet, kunde):  # noqa: F811
    daten = {"art": "firma", "firmenname": "Stadt Köln", "typ": "kunde", "land": "Deutschland"}
    seite = angemeldet.post(
        f"/kontakte/{kunde.id}/bearbeiten", data={**daten, "leitweg_id": "05315-1234-99"}
    ).get_data(as_text=True)
    assert "Prüfziffer" in seite
    antwort = angemeldet.post(
        f"/kontakte/{kunde.id}/bearbeiten", data={**daten, "leitweg_id": "991-33333test-33"}
    )
    assert antwort.status_code == 302 and kunde.leitweg_id == "991-33333TEST-33"


def test_lange_anschrift(angemeldet, entwurf, session):  # noqa: F811
    gewerbe = session.get(Gewerbe, 1)
    assert not any("Sichtfenster" in h for h in pruefhinweise(entwurf, gewerbe))
    entwurf.empfaenger_name = "Gesellschaft zur Förderung der fotografischen Dokumentation e. V."
    entwurf.empfaenger_zusatz = "Abteilung Öffentlichkeitsarbeit und Veranstaltungsmanagement"
    entwurf.empfaenger_land = "Österreich"
    assert any("Sichtfenster" in h for h in pruefhinweise(entwurf, gewerbe))
    session.rollback()


def test_suche_ohne_umlaute(angemeldet, kunde):  # noqa: F811
    from app.services.suchnorm import norm

    assert norm("Köln") == norm("koeln") == norm("KOLN") == "koln"
    assert norm("Straße") == "strasse"
    for text in ("koln", "koeln", "cafe sonnen"):
        seite = angemeldet.get(f"/suche?q={text}").get_data(as_text=True)
        assert "Café Sonnenschein" in seite, text


def test_aenderungsprotokoll(angemeldet, kunde):  # noqa: F811
    seite = angemeldet.get("/protokoll").get_data(as_text=True)
    assert "Kontakt angelegt" in seite and f"/kontakte/{kunde.id}" in seite
    assert angemeldet.get("/protokoll?objekt=kontakt&id=999").status_code == 200


# ---------- Anlagegut korrigieren ----------


def test_anlagegut_korrigieren(angemeldet, admin, session):
    from datetime import date

    from app.services.anlagen import lege_an, verzeichnis
    from app.services.euer import berechne
    from tests.test_afa import JAHR, ausgabe

    buchung = ausgabe(session, admin, 156000)
    lege_an(
        buchung,
        bezeichnung="Kamera",
        art="computer",  # falsch: sofort voll abgeschrieben
        anschaffungsdatum=date(JAHR, 3, 10),
        nutzungsdauer_jahre=1,
        nutzer_id=admin.id,
    )
    assert berechne(JAHR).summe_ausgaben == 156000
    seite = angemeldet.get(f"/buchungen/{buchung.id}").get_data(as_text=True)
    assert "Abschreibung korrigieren" in seite

    antwort = angemeldet.post(f"/buchungen/{buchung.id}/anlagegut/korrigieren")
    neu_id = int(antwort.headers["Location"].split("/")[-2])
    assert neu_id != buchung.id
    from app.models import Buchung

    neu = session.get(Buchung, neu_id)
    assert neu.betrag_cent == 156000 and neu.zahlstatus == "bezahlt" and neu.anlagegut is None
    assert verzeichnis(JAHR) == []
    lege_an(
        neu,
        bezeichnung="Kamera",
        art="beweglich",
        anschaffungsdatum=date(JAHR, 3, 10),
        nutzungsdauer_jahre=7,
        nutzer_id=admin.id,
    )
    assert berechne(JAHR).summe_ausgaben < 156000  # nur der Anteil dieses Jahres
    assert len(verzeichnis(JAHR)) == 1
