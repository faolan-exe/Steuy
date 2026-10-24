import pytest

from app.domain.rundgang import (
    ANFAENGER,
    ERFAHREN,
    EXPERTE,
    SCHRITTE,
    absaetze,
    frage_zum_start,
    schritte_fuer,
)
from app.models import Nutzer
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer


def alle_rechte(_):
    return True


# ---------- Inhalt ----------


def test_schritte_haben_eindeutige_kennungen_und_texte():
    kennungen = [s.kennung for s in SCHRITTE]
    assert len(kennungen) == len(set(kennungen)) >= 20
    for s in SCHRITTE:
        assert s.titel and s.absaetze and all(a.strip() for a in s.absaetze), s.kennung
        assert s.endpunkt


def test_alle_wichtigen_funktionen_kommen_vor():
    text = " ".join(s.titel + " " + " ".join(s.absaetze) for s in SCHRITTE).lower()
    for stichwort in (
        "dashboard",
        "zu prüfen",
        "fragezeichen",
        "firmendaten",
        "bankverbindung",
        "drucklayout",
        "mahnwesen",
        "e-mail",
        "kontakte",
        "artikel",
        "angebot",
        "rechnung",
        "finalisier",
        "zahlung",
        "mahnung",
        "lieferschein",
        "beleg",
        "auswertung",
        "eür",
        "zwei-faktor",
        "sicherung",
        "update",
        "suche",
        "kleinunternehmergrenze",
    ):
        assert stichwort in text, stichwort


def test_stufen_unterscheiden_sich():
    anfaenger = schritte_fuer(ANFAENGER, alle_rechte)
    erfahren = schritte_fuer(ERFAHREN, alle_rechte)
    assert len(anfaenger) > len(erfahren)  # Grundlagen-Schritt nur für Anfänger
    assert [s.kennung for s in erfahren] == [s.kennung for s in schritte_fuer(EXPERTE, alle_rechte)]
    schritt = next(s for s in SCHRITTE if s.einsteiger)
    assert len(absaetze(schritt, ANFAENGER)) > len(absaetze(schritt, ERFAHREN))


def test_schritte_ohne_recht_entfallen():
    ohne = schritte_fuer(ANFAENGER, lambda recht: recht == "ansehen")
    assert all(s.recht in (None, "ansehen") for s in ohne)
    assert len(ohne) < len(schritte_fuer(ANFAENGER, alle_rechte))


@pytest.mark.parametrize(
    ("erfahrung", "kennt", "frage"),
    [
        (ANFAENGER, False, "starten"),
        (ERFAHREN, False, "starten"),
        (None, None, "starten"),
        (EXPERTE, False, "experte"),
        (ANFAENGER, True, "kennt"),
        (EXPERTE, True, "beides"),
    ],
)
def test_frage_zum_start(erfahrung, kennt, frage):
    assert frage_zum_start(erfahrung, kennt) == frage


# ---------- Einrichtung ----------


def einrichten(client, **mehr):
    from tests.test_einrichtung import formular

    return client.post("/einrichtung", data=formular(**mehr))


def test_einrichtung_speichert_antworten_und_startet_bei_anfaengern(client, session):
    antwort = einrichten(client, erfahrung="anfaenger", kennt_steuy="nein")
    assert antwort.headers["Location"].endswith("/rundgang")
    nutzer = session.query(Nutzer).one()
    assert (nutzer.erfahrung, nutzer.kennt_steuy) == ("anfaenger", False)
    weiter = client.get("/rundgang")
    assert weiter.status_code == 302 and weiter.headers["Location"].endswith("/")
    session.refresh(nutzer)
    assert nutzer.rundgang_schritt == 0
    seite = client.get("/").get_data(as_text=True)
    assert 'id="rundgang"' in seite and "Willkommen bei steuy" in seite
    assert "Schritt 1 von" in seite


def test_experte_wird_gefragt(client, session):
    einrichten(client, erfahrung="experte", kennt_steuy="nein")
    seite = client.get("/rundgang").get_data(as_text=True)
    assert "Rundgang trotzdem" in seite and "direkt loslegen" in seite
    assert session.query(Nutzer).one().rundgang_schritt is None


def test_kennt_steuy_wird_gefragt_ob_ueberspringen(client, session):
    einrichten(client, erfahrung="erfahren", kennt_steuy="ja")
    seite = client.get("/rundgang").get_data(as_text=True)
    assert "überspringen" in seite and "Nein, Rundgang ansehen" in seite
    nein = client.post("/rundgang/start")
    assert nein.status_code == 302
    assert session.query(Nutzer).one().rundgang_schritt == 0


def test_ueberspringen_merkt_sich_und_fragt_nicht_mehr(client, session):
    einrichten(client, erfahrung="experte", kennt_steuy="ja")
    client.post("/rundgang/ueberspringen")
    nutzer = session.query(Nutzer).one()
    assert nutzer.rundgang_fertig is True and nutzer.rundgang_schritt is None
    assert client.get("/rundgang").headers["Location"].endswith("/")
    assert 'id="rundgang"' not in client.get("/").get_data(as_text=True)


# ---------- Durchlauf ----------


@pytest.fixture
def mit_rundgang(angemeldet, admin, session):
    admin.erfahrung = ANFAENGER
    session.commit()
    angemeldet.post("/rundgang/start")
    return angemeldet


def test_weiter_zurueck_beenden(mit_rundgang, admin, session):
    client = mit_rundgang
    client.post("/rundgang/weiter")
    session.refresh(admin)
    assert admin.rundgang_schritt == 1
    client.post("/rundgang/zurueck")
    session.refresh(admin)
    assert admin.rundgang_schritt == 0
    client.post("/rundgang/zurueck")  # am Anfang bleibt es beim ersten Schritt
    session.refresh(admin)
    assert admin.rundgang_schritt == 0
    client.post("/rundgang/beenden")
    session.refresh(admin)
    assert admin.rundgang_schritt is None and admin.rundgang_fertig is False


def test_jeder_schritt_ist_eine_erreichbare_seite_und_das_ende_schliesst_ab(
    mit_rundgang, admin, session, app
):
    client = mit_rundgang
    anzahl = len(schritte_fuer(ANFAENGER, alle_rechte))
    for nummer in range(1, anzahl + 1):
        antwort = client.get("/rundgang/schritt")
        assert antwort.status_code == 302
        seite = client.get(antwort.headers["Location"])
        assert seite.status_code == 200, antwort.headers["Location"]
        text = seite.get_data(as_text=True)
        assert f"Schritt {nummer} von {anzahl}" in text
        client.post("/rundgang/weiter")
    session.refresh(admin)
    assert admin.rundgang_schritt is None and admin.rundgang_fertig is True


def test_einsteiger_sehen_mehr_text_als_erfahrene(mit_rundgang, admin, session):
    client = mit_rundgang
    for _ in range(2):
        client.post("/rundgang/weiter")
    anfaenger = client.get("/").get_data(as_text=True)
    admin.erfahrung = ERFAHREN
    session.commit()
    erfahren = client.get("/").get_data(as_text=True)
    assert "Merke dir die Reihenfolge" in anfaenger or "Merke dir" in anfaenger
    assert "Merke dir die Reihenfolge" not in erfahren


def test_profil_stufe_aendern_und_neu_starten(angemeldet, admin, session):
    seite = angemeldet.get("/profil").get_data(as_text=True)
    assert "Rundgang durch steuy" in seite and "Kompletter Anfänger" in seite
    antwort = angemeldet.post(
        "/rundgang/einstellen",
        data={"erfahrung": "erfahren", "kennt_steuy": "ja", "aktion": "starten"},
    )
    assert antwort.status_code == 302
    session.refresh(admin)
    assert (admin.erfahrung, admin.kennt_steuy, admin.rundgang_schritt) == ("erfahren", True, 0)
    kaputt = angemeldet.post(
        "/rundgang/einstellen", data={"erfahrung": "guru"}, follow_redirects=True
    )
    assert "Bitte eine Stufe wählen" in kaputt.get_data(as_text=True)


def test_mitarbeiter_sieht_nur_passende_schritte(client, admin, session):
    neuer_nutzer(session, "mitarbeiter@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "mitarbeiter@x.example", "passwort": ADMIN_PASSWORT})
    nutzer = session.query(Nutzer).filter_by(email="mitarbeiter@x.example").one()
    nutzer.erfahrung = ANFAENGER
    session.commit()
    client.post("/rundgang/start")
    erreicht = []
    for _ in range(60):
        antwort = client.get("/rundgang/schritt")
        if antwort.status_code != 302:
            break
        erreicht.append(client.get(antwort.headers["Location"]).status_code)
        client.post("/rundgang/weiter")
        session.refresh(nutzer)
        if nutzer.rundgang_schritt is None:
            break
    assert erreicht and set(erreicht) == {200}


def test_rundgang_braucht_anmeldung(client, admin):
    assert client.get("/rundgang").status_code == 302
    assert client.post("/rundgang/weiter").status_code in (302, 401, 403)
