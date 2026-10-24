import re
import time

import pyotp
import pytest
from sqlalchemy import select

from app.domain.zwei_faktor import (
    neue_wiederherstellungscodes,
    normalisiere_wiederherstellungscode,
    pruefe_code,
)
from app.models import Gewerbe, Protokoll, Wiederherstellungscode
from app.services.geheimnis import entschluessele
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT, neuer_nutzer

GEHEIMNIS = "JBSWY3DPEHPK3PXP"


# ---------- Domain ----------


def test_code_pruefen_mit_toleranz_und_ohne_wiederholung():
    jetzt = 1_800_000_000.0
    totp = pyotp.TOTP(GEHEIMNIS)
    code = totp.at(jetzt)
    schritt = pruefe_code(GEHEIMNIS, code, None, jetzt)
    assert schritt == int(jetzt // 30)
    assert pruefe_code(GEHEIMNIS, code, schritt, jetzt) is None  # nicht zweimal
    assert pruefe_code(GEHEIMNIS, totp.at(jetzt - 30), None, jetzt) is not None  # 30 s Toleranz
    assert pruefe_code(GEHEIMNIS, totp.at(jetzt - 120), None, jetzt) is None
    assert pruefe_code(GEHEIMNIS, "12345", None, jetzt) is None
    assert pruefe_code(GEHEIMNIS, code[:3] + " " + code[3:], None, jetzt) is not None


def test_wiederherstellungscodes():
    codes = neue_wiederherstellungscodes()
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(re.fullmatch(r"[a-z2-9]{5}-[a-z2-9]{5}", c) for c in codes)
    assert normalisiere_wiederherstellungscode(" ABCDE fghij ") == "abcde-fghij"


# ---------- Einrichtung ----------


def aktueller_code(client, nutzer) -> str:
    with client.application.app_context():
        return pyotp.TOTP(entschluessele(nutzer.totp_geheimnis)).now()


def einrichten(client, nutzer) -> list[str]:
    seite = client.get("/profil/zwei-faktor").get_data(as_text=True)
    assert "<svg" in seite
    antwort = client.post("/profil/zwei-faktor", data={"code": aktueller_code(client, nutzer)})
    return re.findall(r"<code>([a-z2-9]{5}-[a-z2-9]{5})</code>", antwort.get_data(as_text=True))


def test_einrichten(angemeldet, admin, session):
    codes = einrichten(angemeldet, admin)
    assert len(codes) == 10
    assert admin.totp_aktiv
    assert admin.totp_geheimnis and GEHEIMNIS not in admin.totp_geheimnis  # verschlüsselt
    gespeichert = session.execute(select(Wiederherstellungscode.code_hash)).scalars().all()
    assert len(gespeichert) == 10 and all(c not in gespeichert for c in codes)
    assert "zwei_faktor_aktiviert" in session.execute(select(Protokoll.aktion)).scalars().all()


def test_falscher_code_bei_einrichtung(angemeldet, admin):
    angemeldet.get("/profil/zwei-faktor")
    antwort = angemeldet.post("/profil/zwei-faktor", data={"code": "000000"})
    assert "Der Code stimmt nicht" in antwort.get_data(as_text=True)
    assert not admin.totp_aktiv


# ---------- Anmeldung ----------


def neu_anmelden(client, passwort=ADMIN_PASSWORT):
    client.post("/abmelden")
    return client.post("/anmelden", data={"email": ADMIN_EMAIL, "passwort": passwort})


def test_anmeldung_braucht_code(angemeldet, admin):
    einrichten(angemeldet, admin)
    antwort = neu_anmelden(angemeldet)
    assert antwort.headers["Location"].endswith("/anmelden/code")
    assert angemeldet.get("/").status_code == 302  # noch nicht angemeldet
    falsch = angemeldet.post("/anmelden/code", data={"code": "000000"})
    assert "Der Code stimmt nicht" in falsch.get_data(as_text=True)
    admin.totp_letzter_schritt = None  # Code aus der Einrichtung darf hier erneut gelten
    antwort = angemeldet.post("/anmelden/code", data={"code": aktueller_code(angemeldet, admin)})
    assert antwort.status_code == 302
    assert angemeldet.get("/").status_code == 200


def test_code_nicht_zweimal(angemeldet, admin):
    einrichten(angemeldet, admin)
    neu_anmelden(angemeldet)
    admin.totp_letzter_schritt = None
    code = aktueller_code(angemeldet, admin)
    angemeldet.post("/anmelden/code", data={"code": code})
    neu_anmelden(angemeldet)
    antwort = angemeldet.post("/anmelden/code", data={"code": code})
    assert "Der Code stimmt nicht" in antwort.get_data(as_text=True)


def test_wiederherstellungscode_einmalig(angemeldet, admin, session):
    codes = einrichten(angemeldet, admin)
    neu_anmelden(angemeldet)
    assert angemeldet.post("/anmelden/code", data={"code": codes[0].upper()}).status_code == 302
    neu_anmelden(angemeldet)
    antwort = angemeldet.post("/anmelden/code", data={"code": codes[0]})
    assert "Der Code stimmt nicht" in antwort.get_data(as_text=True)
    assert (
        "wiederherstellungscode_benutzt"
        in session.execute(select(Protokoll.aktion)).scalars().all()
    )


def test_codeschritt_laeuft_ab(angemeldet, admin):
    einrichten(angemeldet, admin)
    neu_anmelden(angemeldet)
    with angemeldet.session_transaction() as sitzung:
        sitzung["zweiter_faktor"] = {**sitzung["zweiter_faktor"], "bis": time.time() - 1}
    assert angemeldet.get("/anmelden/code").headers["Location"].endswith("/anmelden")


def test_codes_werden_gesperrt(angemeldet, admin):
    einrichten(angemeldet, admin)
    neu_anmelden(angemeldet)
    for _ in range(5):
        angemeldet.post("/anmelden/code", data={"code": "000000"})
    antwort = angemeldet.post("/anmelden/code", data={"code": aktueller_code(angemeldet, admin)})
    assert antwort.status_code == 429


def test_code_seite_ohne_passwort_schritt(client, admin):
    assert client.get("/anmelden/code").headers["Location"].endswith("/anmelden")


# ---------- Verwalten ----------


def test_ausschalten_braucht_passwort(angemeldet, admin):
    einrichten(angemeldet, admin)
    angemeldet.post("/profil/zwei-faktor/deaktivieren", data={"passwort": "falsch-falsch"})
    assert admin.totp_aktiv
    angemeldet.post("/profil/zwei-faktor/deaktivieren", data={"passwort": ADMIN_PASSWORT})
    assert not admin.totp_aktiv and admin.totp_geheimnis is None


def test_neue_codes(angemeldet, admin):
    alt = einrichten(angemeldet, admin)
    antwort = angemeldet.post("/profil/zwei-faktor/codes", data={"passwort": ADMIN_PASSWORT})
    neu = re.findall(r"<code>([a-z2-9]{5}-[a-z2-9]{5})</code>", antwort.get_data(as_text=True))
    assert len(neu) == 10 and not set(neu) & set(alt)


def test_admin_setzt_zurueck(angemeldet, admin, session, client):
    person = neuer_nutzer(session, "b@x.example", "buchhalter")
    person.totp_aktiv = True
    session.commit()
    angemeldet.post(f"/einstellungen/nutzer/{person.id}/zwei-faktor-zuruecksetzen")
    assert not person.totp_aktiv


def test_pflicht_fuer_alle(angemeldet, admin, session):
    angemeldet.post("/einstellungen/zwei-faktor-pflicht", data={"pflicht": "y"})
    assert session.get(Gewerbe, 1).zwei_faktor_pflicht
    antwort = angemeldet.get("/rechnungen")
    assert antwort.headers["Location"].endswith("/profil/zwei-faktor")
    einrichten(angemeldet, admin)
    assert angemeldet.get("/rechnungen").status_code == 200


def test_pflicht_nur_durch_admin(client, admin, session):
    neuer_nutzer(session, "m@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "m@x.example", "passwort": ADMIN_PASSWORT})
    assert (
        client.post("/einstellungen/zwei-faktor-pflicht", data={"pflicht": "y"}).status_code == 403
    )


# ---------- Passwort ändern ----------


@pytest.mark.parametrize(
    ("daten", "meldung"),
    [
        (
            {"alt": "falsch-falsch", "neu": "ganz-neues-pw", "wiederholen": "ganz-neues-pw"},
            "stimmt nicht",
        ),
        ({"alt": ADMIN_PASSWORT, "neu": "kurz", "wiederholen": "kurz"}, "mindestens 10"),
        (
            {"alt": ADMIN_PASSWORT, "neu": "ganz-neues-pw", "wiederholen": "anderes-pw-x"},
            "nicht überein",
        ),
    ],
)
def test_passwort_aendern_fehler(angemeldet, daten, meldung):
    assert meldung in angemeldet.post("/profil", data=daten).get_data(as_text=True)


def test_passwort_aendern(angemeldet, admin, session):
    angemeldet.post(
        "/profil",
        data={"alt": ADMIN_PASSWORT, "neu": "ganz-neues-pw", "wiederholen": "ganz-neues-pw"},
    )
    assert neu_anmelden(angemeldet).status_code == 200  # altes Passwort geht nicht mehr
    assert neu_anmelden(angemeldet, "ganz-neues-pw").status_code == 302


def test_qr_code_skaliert_mit_ruhezone(angemeldet):
    """Ohne viewBox schneidet das CSS den Code ab, ohne Rand erkennen Apps ihn nicht."""
    seite = angemeldet.get("/profil/zwei-faktor").get_data(as_text=True)
    start = seite.index("<svg", seite.index('class="qrbox"'))
    svg = seite[start : seite.index("</svg>", start)]
    assert "viewBox=" in svg and " width=" not in svg.split(">")[0]
    assert 'fill="#fff"' in svg
