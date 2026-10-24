from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.domain.afa import AfaUngueltig, gwg_grenze_brutto, ist_gwg, plan, restbuchwert
from app.models import Anlagegut
from app.services.anlagen import gwg_grenze_netto, lege_an, ueber_gwg_grenze, verzeichnis
from app.services.buchungen import Buchungsdaten, festschreiben, lege_entwurf_an, storniere
from app.services.euer import berechne, jahre_mit_daten
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_euer import kategorie_id, kz

JAHR = date.today().year


def ausgabe(
    session, admin, betrag, kategorie="Geringwertige Anschaffungen", datum=None, prozent=100
):
    datum = datum or date(JAHR, 3, 10)
    buchung = lege_entwurf_an(
        Buchungsdaten(
            art="ausgabe",
            belegdatum=datum,
            betrag_cent=betrag,
            kategorie_id=kategorie_id(session, kategorie),
            betrieblich_prozent=prozent,
            partner="Elektromarkt",
            beschreibung="Bürostuhl",
        ),
        admin.id,
    )
    return festschreiben(buchung, admin.id, bezahlt_am=datum, zahlungsart="ueberweisung")


# ---------- Domain ----------


def test_gwg_grenze_netto_gegen_brutto():
    assert gwg_grenze_brutto(80000, 19) == 95200
    assert ist_gwg(95200, 80000, 19) and not ist_gwg(95201, 80000, 19)
    assert ist_gwg(80000, 80000, 0) and not ist_gwg(80001, 80000, 0)


def test_linear_zeitanteilig_und_exakt():
    p = plan(120000, date(2025, 10, 15), 3, "beweglich")
    assert p == {2025: 10000, 2026: 40000, 2027: 40000, 2028: 30000}
    assert sum(p.values()) == 120000
    assert restbuchwert(120000, p, 2025) == 110000 and restbuchwert(120000, p, 2028) == 0


def test_cent_rest_landet_exakt():
    p = plan(100001, date(2025, 1, 1), 3, "beweglich")
    assert sum(p.values()) == 100001 and list(p) == [2025, 2026, 2027]


def test_januar_ist_ganzes_jahr_dezember_ein_monat():
    assert plan(130000, date(2025, 1, 31), 13, "beweglich")[2025] == 10000
    assert plan(120000, date(2025, 12, 1), 1, "beweglich") == {2025: 10000, 2026: 110000}


@pytest.mark.parametrize("art", ["computer", "software"])
def test_computer_und_software_voll_im_anschaffungsjahr(art):
    assert plan(250000, date(2025, 12, 20), 5, art) == {2025: 250000}


@pytest.mark.parametrize(
    ("kosten", "dauer", "art"), [(0, 3, "beweglich"), (1000, 0, "beweglich"), (1000, 3, "auto")]
)
def test_ungueltig(kosten, dauer, art):
    with pytest.raises(AfaUngueltig):
        plan(kosten, date(2025, 1, 1), dauer, art)


# ---------- Service und EÜR ----------


def test_gwg_grenze_aus_daten(admin):
    assert gwg_grenze_netto(2025) == 80000
    assert gwg_grenze_netto(2040) == 80000  # neueste bekannte
    assert gwg_grenze_netto(2010) == 80000  # früheste bekannte


def test_nachfrage_nur_ueber_grenze_und_nur_bei_anschaffungen(session, admin):
    assert not ueber_gwg_grenze(ausgabe(session, admin, 95200))
    assert ueber_gwg_grenze(ausgabe(session, admin, 95201))
    assert not ueber_gwg_grenze(ausgabe(session, admin, 200000, kategorie="Werbung"))


def test_anlagegut_ersetzt_ausgabe_in_der_euer(session, admin):
    buchung = ausgabe(session, admin, 156000, datum=date(JAHR, 7, 3))  # 13 Jahre Büromöbel
    assert kz(berechne(JAHR), "132")[0] == 156000  # vorher: voll als GWG
    lege_an(
        buchung,
        bezeichnung="Bürostuhl",
        art="beweglich",
        anschaffungsdatum=date(JAHR, 7, 3),
        nutzungsdauer_jahre=13,
        nutzer_id=admin.id,
    )
    e = berechne(JAHR)
    assert not kz(e, "132")[0]
    assert kz(e, "130")[0] == 6000  # 6 von 156 Monaten
    assert e.summe_ausgaben == 6000
    assert "AfA Bürostuhl (13 Jahre)" in [p.text for p in kz(e, "130")[1]]
    # Folgejahr ohne Zahlung, aber mit AfA
    assert kz(berechne(JAHR + 1), "130")[0] == 12000
    assert JAHR + 12 in jahre_mit_daten()


def test_software_als_immaterielles_wirtschaftsgut(session, admin):
    buchung = ausgabe(session, admin, 120000, kategorie="Software und Abos")
    lege_an(
        buchung,
        bezeichnung="Grafikprogramm",
        art="software",
        anschaffungsdatum=date(JAHR, 3, 10),
        nutzungsdauer_jahre=5,
        nutzer_id=admin.id,
    )
    e = berechne(JAHR)
    assert kz(e, "131")[0] == 120000 and not kz(e, "228")[0]
    assert session.execute(select(Anlagegut)).scalar_one().nutzungsdauer_jahre == 1


def test_storno_hebt_anlagegut_auf(session, admin):
    buchung = ausgabe(session, admin, 156000)
    lege_an(
        buchung,
        bezeichnung="Stuhl",
        art="beweglich",
        anschaffungsdatum=date(JAHR, 3, 10),
        nutzungsdauer_jahre=13,
        nutzer_id=admin.id,
    )
    storniere(buchung, admin.id)
    e = berechne(JAHR)
    assert e.summe_ausgaben == 0 and verzeichnis(JAHR) == []


def test_kein_anlagegut_mit_privatanteil_oder_doppelt(session, admin):
    halb = ausgabe(session, admin, 156000, prozent=50)
    with pytest.raises(AfaUngueltig, match="privatem Anteil"):
        lege_an(
            halb,
            bezeichnung="x",
            art="computer",
            anschaffungsdatum=date(JAHR, 1, 1),
            nutzungsdauer_jahre=1,
            nutzer_id=admin.id,
        )
    voll = ausgabe(session, admin, 156000)
    daten = {
        "bezeichnung": "x",
        "art": "computer",
        "anschaffungsdatum": date(JAHR, 1, 1),
        "nutzungsdauer_jahre": 1,
        "nutzer_id": admin.id,
    }
    lege_an(voll, **daten)
    with pytest.raises(AfaUngueltig, match="schon ein Anlagegut"):
        lege_an(voll, **daten)


def test_anlagegut_unveraenderlich(session, admin):
    buchung = ausgabe(session, admin, 156000)
    lege_an(
        buchung,
        bezeichnung="Stuhl",
        art="beweglich",
        anschaffungsdatum=date(JAHR, 3, 10),
        nutzungsdauer_jahre=13,
        nutzer_id=admin.id,
    )
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text("UPDATE anlagegut SET nutzungsdauer_jahre = 1"))


# ---------- Oberfläche ----------


def test_festschreiben_ueber_grenze_fuehrt_zum_anlagegut(angemeldet, session, admin):
    antwort = angemeldet.post(
        "/buchungen/neu",
        data={
            "art": "ausgabe",
            "kontakt_id": "",
            "partner": "Möbelhaus",
            "belegdatum": date(JAHR, 3, 10).isoformat(),
            "betrag": "1.560,00",
            "betrieblich_prozent": "100",
            "kategorie_id": str(kategorie_id(session, "Geringwertige Anschaffungen")),
            "bereits_bezahlt": "y",
            "bezahlt_am": date(JAHR, 3, 10).isoformat(),
            "zahlungsart": "ueberweisung",
            "aktion": "festschreiben",
        },
    )
    assert "/anlagegut" in antwort.headers["Location"]
    seite = angemeldet.get(antwort.headers["Location"]).get_data(as_text=True)
    assert "Über mehrere Jahre abschreiben" in seite and "Büromöbel" in seite

    url = antwort.headers["Location"]
    formular = {
        "bezeichnung": "Schreibtisch",
        "art": "beweglich",
        "anschaffungsdatum": date(JAHR, 3, 10).isoformat(),
        "nutzungsdauer_jahre": "13",
    }
    vorschau = angemeldet.post(url, data=formular | {"aktion": "vorschau"}).get_data(as_text=True)
    assert "So wird abgeschrieben" in vorschau and "100,00 €" in vorschau  # 10 Monate à 10 €
    angemeldet.post(url, data=formular | {"aktion": "anlegen"})
    gut = session.execute(select(Anlagegut)).scalar_one()
    assert gut.bezeichnung == "Schreibtisch"

    liste = angemeldet.get(f"/auswertung/anlagen?jahr={JAHR}").get_data(as_text=True)
    assert "Schreibtisch" in liste and "Kennzahl 130: 100,00 €" in liste
    buchung = angemeldet.get(f"/buchungen/{gut.buchung_id}").get_data(as_text=True)
    assert "13 Jahre ab" in buchung


def test_nutzungsdauer_pflicht_bei_anderem(angemeldet, session, admin):
    buchung = ausgabe(session, admin, 156000)
    seite = angemeldet.post(
        f"/buchungen/{buchung.id}/anlagegut",
        data={
            "bezeichnung": "Stuhl",
            "art": "beweglich",
            "anschaffungsdatum": date(JAHR, 3, 10).isoformat(),
            "aktion": "anlegen",
        },
    ).get_data(as_text=True)
    assert "Bitte die Nutzungsdauer angeben" in seite


@pytest.mark.parametrize(("rolle", "status"), [("mitarbeiter", 403), ("steuerberater", 200)])
def test_rechte(client, admin, session, rolle, status):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/auswertung/anlagen").status_code == status


def test_abschreiben_nur_ueber_der_gwg_grenze_angeboten(angemeldet, session, admin):
    """Eine 10-€-Gebühr braucht keinen Hinweis auf Abschreibung, ein Laptop schon."""
    klein = ausgabe(session, admin, 1000, kategorie="Gebühren")
    gross = ausgabe(session, admin, 149900)
    seite = angemeldet.get(f"/buchungen/{klein.id}").get_data(as_text=True)
    assert "Über mehrere Jahre abschreiben" not in seite
    seite = angemeldet.get(f"/buchungen/{gross.id}").get_data(as_text=True)
    assert "Über mehrere Jahre abschreiben" in seite
    # Genau an der Grenze (952 € brutto) ist es noch ein GWG
    an_grenze = ausgabe(session, admin, 95200)
    assert "Über mehrere Jahre abschreiben" not in angemeldet.get(
        f"/buchungen/{an_grenze.id}"
    ).get_data(as_text=True)


def test_hinweis_nach_festschreiben_nennt_beide_faelle(angemeldet, session):
    antwort = angemeldet.post(
        "/buchungen/neu",
        data={
            "art": "ausgabe",
            "kontakt_id": "",
            "partner": "Möbelhaus",
            "belegdatum": date(JAHR, 3, 10).isoformat(),
            "betrag": "1.560,00",
            "betrieblich_prozent": "100",
            "kategorie_id": str(kategorie_id(session, "Geringwertige Anschaffungen")),
            "bereits_bezahlt": "y",
            "bezahlt_am": date(JAHR, 3, 10).isoformat(),
            "zahlungsart": "ueberweisung",
            "aktion": "festschreiben",
        },
        follow_redirects=True,
    )
    text_ = antwort.get_data(as_text=True)
    assert "sofort voll (Computer, Software) oder über mehrere Jahre" in text_
    assert "wird deshalb über mehrere Jahre abgeschrieben" not in text_
