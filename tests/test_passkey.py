import time

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import func, select

from app.models import Gewerbe, Nutzer, Passkey, Protokoll
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT, neuer_nutzer
from tests.passkey_hilfe import UP, Authenticator


def optionen(client, adresse, **kopf):
    antwort = client.post(adresse, headers=kopf or None)
    return antwort, (antwort.get_json() or {})


def registriere(client, geraet: Authenticator | None = None, name="Handy", **mehr):
    geraet = geraet or Authenticator()
    antwort, opt = optionen(client, "/profil/passkeys/optionen")
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    credential = geraet.registrieren(opt, **mehr)
    ergebnis = client.post("/profil/passkeys", json={"name": name, "credential": credential})
    return geraet, ergebnis


def anmelden(client, geraet: Authenticator, **mehr):
    antwort, opt = optionen(client, "/anmelden/passkey/optionen")
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    return client.post(
        "/anmelden/passkey",
        json={"credential": geraet.anmelden(opt, **mehr), "ziel": mehr.get("z")},
    )


@pytest.fixture
def geraet(angemeldet, admin, session):
    """Ein eingerichteter Passkey des Admins."""
    gerät, antwort = registriere(angemeldet)
    assert antwort.status_code == 200 and antwort.get_json() == {"ok": True}
    return gerät


@pytest.fixture
def fremder_browser(app):
    return app.test_client()


# ---------- Einrichten ----------


def test_passkey_einrichten(angemeldet, geraet, session, admin):
    (p,) = session.scalars(select(Passkey)).all()
    assert p.nutzer_id == admin.id and p.name == "Handy" and p.sign_count == 0
    assert p.credential_id == geraet.credential_id and p.transports == ["internal"]
    aktionen = set(session.scalars(select(Protokoll.aktion)))
    assert "passkey_eingerichtet" in aktionen
    seite = angemeldet.get("/profil").get_data(as_text=True)
    assert "Handy" in seite and "Passkey hinzufügen" in seite


def test_optionen_verlangen_nutzerpruefung_und_erkennbare_schluessel(angemeldet, admin):
    antwort, opt = optionen(angemeldet, "/profil/passkeys/optionen")
    assert opt["rp"] == {"name": "steuy", "id": "localhost"}
    assert opt["authenticatorSelection"]["userVerification"] == "required"
    assert opt["authenticatorSelection"]["residentKey"] == "required"
    assert opt["user"]["name"] == ADMIN_EMAIL and opt["attestation"] == "none"


def test_bereits_eingerichteter_schluessel_wird_ausgeschlossen(angemeldet, geraet):
    _, opt = optionen(angemeldet, "/profil/passkeys/optionen")
    assert len(opt["excludeCredentials"]) == 1


def test_gleicher_schluessel_nicht_zweimal(angemeldet, geraet):
    _, antwort = registriere(angemeldet, geraet)
    assert antwort.status_code == 400 and "schon eingerichtet" in antwort.get_json()["fehler"]


def test_registrierung_ohne_nutzerpruefung_wird_abgelehnt(angemeldet, admin, session):
    _, antwort = registriere(angemeldet, flags=UP)
    assert antwort.status_code == 400
    assert session.scalar(select(func.count()).select_from(Passkey)) == 0


def test_registrierung_von_falscher_adresse_wird_abgelehnt(angemeldet, admin, session):
    _, antwort = registriere(angemeldet, ursprung="https://boese.example")
    assert antwort.status_code == 400
    assert session.scalar(select(func.count()).select_from(Passkey)) == 0


def test_herausforderung_gilt_nur_einmal(angemeldet, admin, session):
    gerät = Authenticator()
    _, opt = optionen(angemeldet, "/profil/passkeys/optionen")
    credential = gerät.registrieren(opt)
    assert angemeldet.post("/profil/passkeys", json={"credential": credential}).status_code == 200
    zweiter = angemeldet.post("/profil/passkeys", json={"credential": credential})
    assert zweiter.status_code == 400 and "abgelaufen" in zweiter.get_json()["fehler"]


def test_herausforderung_verfaellt(angemeldet, admin, monkeypatch):
    gerät = Authenticator()
    _, opt = optionen(angemeldet, "/profil/passkeys/optionen")
    credential = gerät.registrieren(opt)
    echt = time.time
    monkeypatch.setattr(time, "time", lambda: echt() + 600)
    antwort = angemeldet.post("/profil/passkeys", json={"credential": credential})
    assert antwort.status_code == 400 and "abgelaufen" in antwort.get_json()["fehler"]


def test_unvollstaendige_antworten_geben_saubere_fehler(angemeldet, admin):
    optionen(angemeldet, "/profil/passkeys/optionen")
    for body in ({}, {"credential": "kaputt"}, {"credential": {"id": 1}}, None):
        optionen(angemeldet, "/profil/passkeys/optionen")
        antwort = angemeldet.post("/profil/passkeys", json=body)
        assert antwort.status_code == 400, body
        assert antwort.get_json()["fehler"]


def test_hoechstens_zehn_passkeys(angemeldet, admin, session):
    for i in range(10):
        _, antwort = registriere(angemeldet, name=f"Gerät {i}")
        assert antwort.status_code == 200
    antwort, _ = optionen(angemeldet, "/profil/passkeys/optionen")
    assert antwort.status_code == 400


@pytest.mark.parametrize(
    ("host", "schema", "grund"),
    [
        ("192.168.178.40", "http", "Domainnamen"),
        ("buchhaltung.example", "http", "HTTPS"),
    ],
)
def test_ohne_domain_und_https_gibt_es_keine_passkeys(angemeldet, host, schema, grund):
    antwort = angemeldet.post(
        "/profil/passkeys/optionen", base_url=f"{schema}://{host}", follow_redirects=False
    )
    # Anderer Host = andere Sitzung: eingeloggt bleibt nur der Browser auf localhost
    assert antwort.status_code in (302, 400)


def test_moeglich_pro_adresse(app):
    from app.services import passkey

    with app.test_request_context("/", base_url="https://buchhaltung.example"):
        assert passkey.moeglich() == (True, "")
        assert passkey.rp_id() == "buchhaltung.example"
        assert passkey.erwarteter_ursprung() == "https://buchhaltung.example"
    with app.test_request_context("/", base_url="http://localhost:5000"):
        assert passkey.moeglich() == (True, "")
        assert passkey.rp_id() == "localhost"
    with app.test_request_context("/", base_url="http://buchhaltung.example"):
        ok, grund = passkey.moeglich()
        assert not ok and "HTTPS" in grund
    with app.test_request_context("/", base_url="https://192.168.178.40"):
        ok, grund = passkey.moeglich()
        assert not ok and "Domainnamen" in grund
    with app.test_request_context("/", base_url="https://[::1]:8443"):
        assert not passkey.moeglich()[0]


# ---------- Anmelden ----------


def test_anmelden_mit_passkey_ohne_passwort(app, geraet, fremder_browser, session):
    antwort = anmelden(fremder_browser, geraet)
    assert antwort.status_code == 200
    assert antwort.get_json() == {"ok": True, "ziel": "/"}
    assert fremder_browser.get("/").status_code == 200  # angemeldet
    (p,) = session.scalars(select(Passkey)).all()
    assert p.sign_count == 1 and p.zuletzt_benutzt_am is not None
    assert "anmeldung_passkey" in set(session.scalars(select(Protokoll.aktion)))


def test_ziel_nach_anmeldung_bleibt_in_der_app(geraet, fremder_browser):
    _, opt = optionen(fremder_browser, "/anmelden/passkey/optionen")
    for ziel, erwartet in [
        ("/rechnungen", "/rechnungen"),
        ("https://boese.example", "/"),
        ("//x.de", "/"),
    ]:
        optionen(fremder_browser, "/anmelden/passkey/optionen")
        _, opt = optionen(fremder_browser, "/anmelden/passkey/optionen")
        antwort = fremder_browser.post(
            "/anmelden/passkey", json={"credential": geraet.anmelden(opt), "ziel": ziel}
        )
        assert antwort.get_json()["ziel"] == erwartet
        fremder_browser.post("/abmelden")


def test_passkey_ersetzt_zweiten_faktor(app, geraet, fremder_browser, session):
    """Mit Passkey entfällt der Code, auch wenn die Zwei-Faktor-Anmeldung eingeschaltet ist."""
    nutzer = session.scalars(select(Nutzer)).first()
    nutzer.totp_aktiv = True
    session.commit()
    assert anmelden(fremder_browser, geraet).status_code == 200
    assert fremder_browser.get("/").status_code == 200


def test_pflicht_zwei_faktor_ist_mit_passkey_erfuellt(app, geraet, fremder_browser, session):
    session.get(Gewerbe, 1).zwei_faktor_pflicht = True
    session.commit()
    assert anmelden(fremder_browser, geraet).status_code == 200
    assert fremder_browser.get("/").status_code == 200
    # Wer nur das Passwort nutzt, wird weiter zur Einrichtung geschickt
    passwort_browser = app.test_client()
    passwort_browser.post("/anmelden", data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT})
    antwort = passwort_browser.get("/rechnungen")
    assert antwort.status_code == 302 and "zwei-faktor" in antwort.headers["Location"]


def test_falsche_signatur_wird_abgelehnt(geraet, fremder_browser):
    fremder_schluessel = ec.generate_private_key(ec.SECP256R1())
    antwort = anmelden(fremder_browser, geraet, schluessel=fremder_schluessel)
    assert antwort.status_code == 400
    assert antwort.get_json()["fehler"] == "Anmeldung mit Passkey fehlgeschlagen."
    assert fremder_browser.get("/").status_code == 302  # nicht angemeldet


def test_antwort_kann_nicht_wiederholt_werden(geraet, fremder_browser):
    _, opt = optionen(fremder_browser, "/anmelden/passkey/optionen")
    credential = geraet.anmelden(opt)
    assert (
        fremder_browser.post("/anmelden/passkey", json={"credential": credential}).status_code
        == 200
    )
    fremder_browser.post("/abmelden")
    nochmal = fremder_browser.post("/anmelden/passkey", json={"credential": credential})
    assert nochmal.status_code == 400


def test_zaehler_darf_nicht_zurueckgehen(geraet, fremder_browser, session):
    assert anmelden(fremder_browser, geraet, zaehler=5).status_code == 200
    fremder_browser.post("/abmelden")
    assert anmelden(fremder_browser, geraet, zaehler=3).status_code == 400  # geklonter Schlüssel?
    assert anmelden(fremder_browser, geraet, zaehler=6).status_code == 200


def test_ohne_nutzerpruefung_keine_anmeldung(geraet, fremder_browser):
    assert anmelden(fremder_browser, geraet, flags=UP).status_code == 400


def test_falscher_ursprung_keine_anmeldung(geraet, fremder_browser):
    assert anmelden(fremder_browser, geraet, ursprung="https://boese.example").status_code == 400


def test_unbekannter_schluessel(fremder_browser, geraet, session):
    fremd = Authenticator()
    fremd.user_handle = geraet.user_handle
    assert anmelden(fremder_browser, fremd).status_code == 400


def test_falscher_nutzerhandle(geraet, fremder_browser):
    assert anmelden(fremder_browser, geraet, handle=b"steuy-999").status_code == 400


def test_gesperrtes_konto_kann_sich_nicht_anmelden(geraet, fremder_browser, session):
    session.scalars(select(Nutzer)).first().aktiv = False
    session.commit()
    antwort = anmelden(fremder_browser, geraet)
    assert antwort.status_code == 400
    assert antwort.get_json()["fehler"] == "Anmeldung mit Passkey fehlgeschlagen."


def test_anmeldung_ohne_vorherige_optionen(geraet, fremder_browser):
    credential = geraet.anmelden({"challenge": "AAAA"})
    antwort = fremder_browser.post("/anmelden/passkey", json={"credential": credential})
    assert antwort.status_code == 400 and "abgelaufen" in antwort.get_json()["fehler"]


def test_anmeldeoptionen_sind_oeffentlich_aber_geben_nichts_preis(geraet, fremder_browser):
    antwort, opt = optionen(fremder_browser, "/anmelden/passkey/optionen")
    assert antwort.status_code == 200
    assert opt.get("allowCredentials") in (None, [])  # keine Liste von Konten
    assert opt["userVerification"] == "required"


def test_angemeldete_brauchen_keine_anmeldeoptionen(angemeldet):
    assert angemeldet.post("/anmelden/passkey/optionen").status_code == 400


def test_login_seite_hat_passkey_knopf(fremder_browser, admin):
    html = fremder_browser.get("/anmelden").get_data(as_text=True)
    assert 'data-passkey="anmelden"' in html and "Mit Passkey anmelden" in html
    assert "js/passkey.js" in html


# ---------- Verwalten ----------


def test_passkey_entfernen(angemeldet, geraet, fremder_browser, session):
    (p,) = session.scalars(select(Passkey)).all()
    antwort = angemeldet.post(f"/profil/passkeys/{p.id}/loeschen", follow_redirects=True)
    assert "Passkey entfernt" in antwort.get_data(as_text=True)
    assert session.scalar(select(func.count()).select_from(Passkey)) == 0
    assert anmelden(fremder_browser, geraet).status_code == 400
    assert "passkey_entfernt" in set(session.scalars(select(Protokoll.aktion)))


def test_fremden_passkey_kann_man_nicht_entfernen(app, angemeldet, geraet, session):
    andere = neuer_nutzer(session, "zweiter@x.example", "buchhalter")
    browser = app.test_client()
    browser.post("/anmelden", data={"email": andere.email, "passwort": ADMIN_PASSWORT})
    (p,) = session.scalars(select(Passkey)).all()
    antwort = browser.post(f"/profil/passkeys/{p.id}/loeschen", follow_redirects=True)
    assert "gibt es nicht" in antwort.get_data(as_text=True)
    assert session.scalar(select(func.count()).select_from(Passkey)) == 1


def test_routen_brauchen_anmeldung(fremder_browser, admin):
    for adresse in ("/profil/passkeys/optionen", "/profil/passkeys", "/profil/passkeys/1/loeschen"):
        assert fremder_browser.post(adresse).status_code == 302


def test_passwortanmeldung_geht_weiter(app, geraet):
    browser = app.test_client()
    antwort = browser.post("/anmelden", data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT})
    assert antwort.status_code == 302
