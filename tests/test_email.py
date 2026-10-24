from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.domain.mail import EmailUngueltig, baue_nachricht, pruefe_adresse, vorlage
from app.models import Gewerbe, Protokoll, Versand
from app.services.geheimnis import entschluessele
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_mahnwesen import HEUTE, mahnen
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401


@pytest.fixture
def ausgang(app):
    with app.app_context():
        liste = app.extensions.setdefault("mail_ausgang", [])
        liste.clear()
        yield liste


@pytest.fixture
def mail_eingerichtet(session, admin):
    gewerbe = session.get(Gewerbe, 1)
    gewerbe.smtp_server = "smtp.example.de"
    gewerbe.mail_absender = "rechnung@werkstatt.example"
    session.commit()
    return gewerbe


# ---------- Domain ----------


@pytest.mark.parametrize("adresse", ["", "kein-at", "a@b", "a b@c.de", "a@b.de\nBcc: x@y.de"])
def test_ungueltige_adressen(adresse):
    with pytest.raises(EmailUngueltig):
        pruefe_adresse(adresse)


def test_nachricht_mit_anhang_und_ohne_kopfzeilen_einschleusung():
    from app.domain.mail import Anhang

    nachricht = baue_nachricht(
        absender="rechnung@werkstatt.example",
        absender_name="Werkstatt Müller",
        an="kunde@example.de",
        betreff="Rechnung RE0001\nBcc: boese@example.de",
        text="Hallo",
        kopie_an="ich@werkstatt.example",
        antwort_an="info@werkstatt.example",
        anhaenge=(Anhang("Rechnung-RE0001.pdf", b"%PDF-1.4"),),
    )
    assert nachricht["Subject"] == "Rechnung RE0001 Bcc: boese@example.de"
    assert nachricht["To"] == "kunde@example.de"
    assert nachricht["Bcc"] == "ich@werkstatt.example"
    assert nachricht["Reply-To"] == "info@werkstatt.example"
    assert "Werkstatt" in nachricht["From"]
    (anhang,) = list(nachricht.iter_attachments())
    assert anhang.get_filename() == "Rechnung-RE0001.pdf"
    assert anhang.get_content() == b"%PDF-1.4"


def test_vorlagen_fuellen_platzhalter():
    werte = {
        "nummer": "RE0001",
        "firma": "Werkstatt",
        "inhaber": "Mia Muster",
        "betrag": "152,20 €",
        "faellig": "05.11.2026",
        "gueltig": "",
        "bezeichnung": "",
        "frist": "",
    }
    betreff, text_ = vorlage("rechnung", werte)
    assert betreff == "Rechnung RE0001 von Werkstatt"
    assert "152,20 €" in text_ and "05.11.2026" in text_ and "Mia Muster" in text_


# ---------- Einstellungen ----------


def test_einstellungen_passwort_verschluesselt(angemeldet, admin, session, app):
    antwort = angemeldet.post(
        "/einstellungen/email",
        data={
            "smtp_server": "smtp.example.de",
            "smtp_port": "587",
            "smtp_verschluesselung": "starttls",
            "smtp_benutzer": "ich@werkstatt.example",
            "smtp_passwort": "geheim-123",
            "mail_absender": "ich@werkstatt.example",
        },
    )
    assert antwort.status_code == 302
    gewerbe = session.get(Gewerbe, 1)
    assert gewerbe.smtp_passwort != "geheim-123"
    with app.app_context():
        assert entschluessele(gewerbe.smtp_passwort) == "geheim-123"
    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "mail_einstellungen")
    ).scalar_one()
    assert "geheim-123" not in str(eintrag.details)
    # Leeres Passwortfeld behält das gespeicherte
    seite = angemeldet.get("/einstellungen/email").get_data(as_text=True)
    assert "geheim-123" not in seite and "eingerichtet" in seite
    angemeldet.post(
        "/einstellungen/email",
        data={
            "smtp_server": "smtp.example.de",
            "smtp_port": "465",
            "smtp_verschluesselung": "ssl",
            "smtp_benutzer": "ich@werkstatt.example",
            "smtp_passwort": "",
            "mail_absender": "ich@werkstatt.example",
        },
    )
    session.refresh(gewerbe)
    with app.app_context():
        assert gewerbe.smtp_port == 465 and entschluessele(gewerbe.smtp_passwort) == "geheim-123"


def test_absender_pflicht_mit_server(angemeldet):
    seite = angemeldet.post(
        "/einstellungen/email",
        data={"smtp_server": "smtp.example.de", "smtp_port": "587", "smtp_verschluesselung": "ssl"},
    ).get_data(as_text=True)
    assert "Bitte die Adresse angeben" in seite


def test_test_mail(angemeldet, admin, mail_eingerichtet, ausgang):
    angemeldet.post("/einstellungen/email/test")
    (mail,) = ausgang
    assert mail["To"] == admin.email and "funktioniert" in mail.get_content()


# ---------- Belege senden ----------


def test_rechnung_senden(angemeldet, rechnung, admin, mail_eingerichtet, ausgang, session):  # noqa: F811
    rechnung.kontakt.email = "kunde@example.de"
    session.commit()
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}/senden").get_data(as_text=True)
    assert "kunde@example.de" in seite and f"Rechnung {rechnung.nummer}" in seite

    antwort = angemeldet.post(
        f"/rechnungen/{rechnung.id}/senden",
        data={
            "an": "kunde@example.de",
            "kopie_an_mich": "y",
            "betreff": f"Rechnung {rechnung.nummer}",
            "text": "Hallo, anbei die Rechnung.",
        },
    )
    assert antwort.status_code == 302
    (mail,) = ausgang
    assert mail["To"] == "kunde@example.de" and mail["Bcc"] == admin.email
    (anhang,) = list(mail.iter_attachments())
    assert anhang.get_content().startswith(b"%PDF")

    versand = session.execute(select(Versand)).scalar_one()
    assert versand.erfolgreich and versand.rechnung_id == rechnung.id
    detail = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert "an kunde@example.de" in detail and 'id="versand"' in detail


def test_mahnung_senden(angemeldet, rechnung, admin, app, mail_eingerichtet, ausgang):  # noqa: F811
    mahnung = mahnen(rechnung, admin, app, HEUTE + timedelta(days=30))
    url = f"/rechnungen/{rechnung.id}/mahnungen/{mahnung.id}/senden"
    seite = angemeldet.get(url).get_data(as_text=True)
    assert f"{mahnung.bezeichnung} zu Rechnung {rechnung.nummer}" in seite
    angemeldet.post(url, data={"an": "k@example.de", "betreff": "Erinnerung", "text": "Bitte"})
    (mail,) = ausgang
    assert (
        list(mail.iter_attachments())[0]
        .get_filename()
        .startswith(mahnung.bezeichnung.replace(" ", "-"))
    )


def test_ohne_einrichtung_hinweis(angemeldet, rechnung):  # noqa: F811
    antwort = angemeldet.get(f"/rechnungen/{rechnung.id}/senden", follow_redirects=True)
    assert "E-Mail-Versand einrichten" in antwort.get_data(as_text=True)


def test_fehler_wird_protokolliert(angemeldet, rechnung, app, mail_eingerichtet, session):  # noqa: F811
    app.config["MAIL_TESTBETRIEB"] = False
    mail_eingerichtet.smtp_server = "127.0.0.1"
    mail_eingerichtet.smtp_port = 1  # dort lauscht nichts
    mail_eingerichtet.smtp_verschluesselung = "keine"
    session.commit()
    try:
        antwort = angemeldet.post(
            f"/rechnungen/{rechnung.id}/senden",
            data={"an": "k@example.de", "betreff": "Rechnung", "text": "Hallo"},
        )
    finally:
        app.config["MAIL_TESTBETRIEB"] = True
    assert antwort.status_code == 422
    assert "nicht erreichbar" in antwort.get_data(as_text=True)
    versand = session.execute(select(Versand)).scalar_one()
    assert versand.erfolgreich is False and "nicht erreichbar" in versand.fehler


def test_versand_unveraenderlich(angemeldet, rechnung, mail_eingerichtet, ausgang, session):  # noqa: F811
    angemeldet.post(
        f"/rechnungen/{rechnung.id}/senden",
        data={"an": "k@example.de", "betreff": "Rechnung", "text": "Hallo"},
    )
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text("UPDATE versand SET an = 'x@y.de'"))
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text("DELETE FROM versand"))


@pytest.mark.parametrize(("rolle", "status"), [("mitarbeiter", 403), ("buchhalter", 200)])
def test_rechte(client, rechnung, session, mail_eingerichtet, rolle, status):  # noqa: F811
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/abmelden")
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get(f"/rechnungen/{rechnung.id}/senden").status_code == status
    assert client.get("/einstellungen/email").status_code == 403
