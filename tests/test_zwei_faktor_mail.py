# ruff: noqa: F811  (Fixtures werden importiert und als Parameter genutzt)
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.zwei_faktor import neuer_mail_code
from app.models import Gewerbe, Protokoll, Wiederherstellungscode
from app.services.zwei_faktor import ZweiFaktorFehler, sende_mail_code
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT
from tests.test_email import ausgang, mail_eingerichtet  # noqa: F401


def code_aus(mail) -> str:
    treffer = re.search(r"Code lautet: (\d{3}) (\d{3})", mail.get_content())
    return treffer.group(1) + treffer.group(2)


def einrichten(angemeldet, ausgang) -> list[str]:
    angemeldet.get("/profil/zwei-faktor/mail")
    seite = angemeldet.post("/profil/zwei-faktor/mail", data={"code": code_aus(ausgang[-1])})
    return re.findall(r"<li><code>([^<]+)</code></li>", seite.get_data(as_text=True))


def anmelden(client):
    client.post("/abmelden")
    return client.post("/anmelden", data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT})


# ---------- Domain ----------


def test_mail_code_sechs_ziffern_mit_fuehrender_null():
    codes = {neuer_mail_code() for _ in range(200)}
    assert all(len(c) == 6 and c.isdigit() for c in codes)
    assert len(codes) > 150


# ---------- Einrichtung ----------


def test_einrichten_und_anmelden(angemeldet, admin, mail_eingerichtet, ausgang, session):
    codes = einrichten(angemeldet, ausgang)
    assert len(codes) == 10
    session.refresh(admin)
    assert admin.totp_aktiv and admin.zwei_faktor_art == "mail"
    assert admin.totp_geheimnis is None
    assert "per E-Mail an" in angemeldet.get("/profil").get_data(as_text=True)

    antwort = anmelden(angemeldet)
    assert antwort.headers["Location"].endswith("/anmelden/code")
    mail = ausgang[-1]
    assert mail["To"] == admin.email and mail["Subject"] == "Dein Anmeldecode für steuy"
    seite = angemeldet.get("/anmelden/code").get_data(as_text=True)
    assert "per E-Mail geschickt" in seite and "Code erneut senden" in seite

    antwort = angemeldet.post("/anmelden/code", data={"code": code_aus(mail)})
    assert antwort.status_code == 302 and antwort.headers["Location"] == "/"
    assert angemeldet.get("/").status_code == 200


def test_code_nur_einmal_und_nur_zehn_minuten(
    angemeldet, admin, mail_eingerichtet, ausgang, session
):
    einrichten(angemeldet, ausgang)
    anmelden(angemeldet)
    code = code_aus(ausgang[-1])
    # abgelaufen
    session.refresh(admin)
    admin.mail_code_bis = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    seite = angemeldet.post("/anmelden/code", data={"code": code}).get_data(as_text=True)
    assert "Der Code stimmt nicht" in seite

    # neuer Code, einmal gültig
    admin.mail_code_gesendet_am = None
    session.commit()
    angemeldet.post("/anmelden/code/neu")
    neu = code_aus(ausgang[-1])
    assert angemeldet.post("/anmelden/code", data={"code": neu}).status_code == 302
    anmelden(angemeldet)
    admin.mail_code_gesendet_am = None
    session.commit()
    assert angemeldet.post("/anmelden/code", data={"code": neu}).status_code == 200


def test_erneut_senden_hoechstens_jede_minute(admin, mail_eingerichtet, ausgang, app, session):
    jetzt = datetime.now(UTC)
    with app.app_context():
        sende_mail_code(admin, jetzt)
        with pytest.raises(ZweiFaktorFehler, match="kurz warten"):
            sende_mail_code(admin, jetzt + timedelta(seconds=30))
        sende_mail_code(admin, jetzt + timedelta(seconds=61))
        # Ist der Code verbraucht, darf sofort ein neuer kommen (z. B. direkt nach der Einrichtung)
        admin.mail_code_hash = None
        sende_mail_code(admin, jetzt + timedelta(seconds=62))
    assert len(ausgang) == 3


def test_wiederherstellungscode_geht_auch(angemeldet, admin, mail_eingerichtet, ausgang, session):
    codes = einrichten(angemeldet, ausgang)
    anmelden(angemeldet)
    assert angemeldet.post("/anmelden/code", data={"code": codes[0]}).status_code == 302
    benutzt = (
        session.execute(
            select(Wiederherstellungscode).where(Wiederherstellungscode.benutzt_am.is_not(None))
        )
        .scalars()
        .all()
    )
    assert len(benutzt) == 1


def test_falsche_codes_fuehren_zur_sperre(angemeldet, admin, mail_eingerichtet, ausgang):
    einrichten(angemeldet, ausgang)
    anmelden(angemeldet)
    status = [
        angemeldet.post("/anmelden/code", data={"code": "000000"}).status_code for _ in range(10)
    ]
    assert 429 in status


def test_ohne_mail_einrichtung_nur_app(angemeldet, admin):
    antwort = angemeldet.get("/profil/zwei-faktor/mail", follow_redirects=True)
    seite = antwort.get_data(as_text=True)
    assert "E-Mail-Versand eingerichtet" in seite
    assert "Code per E-Mail bekommen" not in angemeldet.get("/profil/zwei-faktor").get_data(
        as_text=True
    )


def test_app_seite_bietet_mail_an(angemeldet, mail_eingerichtet):
    seite = angemeldet.get("/profil/zwei-faktor").get_data(as_text=True)
    assert "Stattdessen einen Code per E-Mail bekommen" in seite


def test_mailausfall_beim_anmelden(angemeldet, admin, mail_eingerichtet, ausgang, session, app):
    einrichten(angemeldet, ausgang)
    mail_eingerichtet.smtp_server = "127.0.0.1"
    mail_eingerichtet.smtp_port = 1
    mail_eingerichtet.smtp_verschluesselung = "keine"
    session.commit()
    app.config["MAIL_TESTBETRIEB"] = False
    try:
        anmelden(angemeldet)
        seite = angemeldet.get("/anmelden/code").get_data(as_text=True)
    finally:
        app.config["MAIL_TESTBETRIEB"] = True
    assert "Wiederherstellungscode" in seite and "nicht verschickt werden" in seite


def test_admin_setzt_zurueck(angemeldet, admin, mail_eingerichtet, ausgang, session):
    einrichten(angemeldet, ausgang)
    from app.services.zwei_faktor import deaktiviere

    deaktiviere(admin, admin.id)
    assert admin.zwei_faktor_art == "app" and admin.mail_code_hash is None
    assert session.execute(
        select(Protokoll).where(Protokoll.aktion == "zwei_faktor_aktiviert")
    ).scalar_one().details == {"art": "mail"}


def test_pflicht_erlaubt_mail_einrichtung(angemeldet, admin, mail_eingerichtet, ausgang, session):
    session.get(Gewerbe, 1).zwei_faktor_pflicht = True
    session.commit()
    assert angemeldet.get("/").headers["Location"].endswith("/profil/zwei-faktor")
    assert angemeldet.get("/profil/zwei-faktor/mail").status_code == 200
