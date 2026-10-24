# ruff: noqa: F811  (Fixtures werden importiert und als Parameter genutzt)
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.erinnerung import faellig, wochenbeginn, zeilen
from app.models import Protokoll
from app.services.erinnerung import sende_wochenmails
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_email import ausgang, mail_eingerichtet  # noqa: F401
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

# Ein Montag und die Woche drumherum
MONTAG_FRUEH = datetime(2026, 10, 19, 5, 59, tzinfo=UTC)
MONTAG = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


# ---------- Domain ----------


def test_wochenbeginn_montag_sechs_uhr_utc():
    assert wochenbeginn(MONTAG) == MONTAG
    assert wochenbeginn(MONTAG + timedelta(days=6, hours=17)) == MONTAG
    assert wochenbeginn(MONTAG_FRUEH) == MONTAG - timedelta(days=7)


@pytest.mark.parametrize(
    ("zuletzt", "jetzt", "erwartet"),
    [
        (None, MONTAG, True),
        (MONTAG, MONTAG + timedelta(hours=3), False),  # Zeitplan läuft stündlich
        (MONTAG, MONTAG + timedelta(days=6, hours=23), False),
        (MONTAG, MONTAG + timedelta(days=7), True),  # nächster Montag
        (MONTAG - timedelta(days=7), MONTAG_FRUEH, False),  # Montag vor 6 Uhr
    ],
)
def test_hoechstens_eine_mail_je_woche(zuletzt, jetzt, erwartet):
    assert faellig(zuletzt, jetzt) is erwartet


def test_zeilen_einzahl_mehrzahl_und_leere():
    assert zeilen([(1, "Beleg", "Belege"), (0, "x", "y"), (3, "Mahnung", "Mahnungen")]) == [
        "- 1 Beleg",
        "- 3 Mahnungen",
    ]


# ---------- Service ----------


def test_mail_mit_offenen_punkten(rechnung, admin, mail_eingerichtet, ausgang, app, session):  # noqa: F811
    app.config["BASIS_URL"] = "https://buch.example.de/"
    try:
        with app.app_context():
            assert sende_wochenmails() == 1
    finally:
        app.config["BASIS_URL"] = ""
    (mail,) = ausgang
    assert mail["To"] == admin.email
    inhalt = mail.get_content()
    assert "1 offene Rechnung" in inhalt
    assert "https://buch.example.de/zu-pruefen" in inhalt
    assert "Profil → E-Mail" in inhalt
    session.refresh(admin)
    assert admin.wochenmail_gesendet_am is not None
    assert session.execute(
        select(Protokoll).where(Protokoll.aktion == "wochenmail_gesendet")
    ).scalar_one()
    # Zweiter Lauf in derselben Woche schickt nichts
    with app.app_context():
        assert sende_wochenmails() == 0
    assert len(ausgang) == 1


def test_nichts_zu_pruefen_keine_mail(admin, mail_eingerichtet, ausgang, app):  # noqa: F811
    with app.app_context():
        assert sende_wochenmails() == 0
    assert ausgang == []


def test_ohne_mail_einrichtung_nichts(rechnung, admin, ausgang, app):  # noqa: F811
    with app.app_context():
        assert sende_wochenmails() == 0


def test_nur_mit_arbeitsrechten_und_abbestellbar(
    rechnung,
    admin,
    mail_eingerichtet,
    ausgang,
    app,
    session,  # noqa: F811
):
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    neuer_nutzer(session, "buch@x.example", "buchhalter")
    admin.wochenmail = False
    session.commit()
    with app.app_context():
        assert sende_wochenmails() == 1
    assert [m["To"] for m in ausgang] == ["buch@x.example"]


def test_profil_schalter(angemeldet, admin, session):
    seite = angemeldet.get("/profil").get_data(as_text=True)
    assert "Wöchentliche Zusammenfassung" in seite
    angemeldet.post("/profil/wochenmail", data={})
    session.refresh(admin)
    assert admin.wochenmail is False
    angemeldet.post("/profil/wochenmail", data={"wochenmail": "y"})
    session.refresh(admin)
    assert admin.wochenmail is True


def test_cli_befehl(app, rechnung, mail_eingerichtet, ausgang):  # noqa: F811
    ergebnis = app.test_cli_runner().invoke(args=["erinnerungen"])
    assert "Wochenmails verschickt: 1" in ergebnis.output


def test_jeder_darf_abbestellen(client, admin, session):
    neuer_nutzer(session, "ma@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "ma@x.example", "passwort": ADMIN_PASSWORT})
    assert client.post("/profil/wochenmail", data={}).status_code == 302
