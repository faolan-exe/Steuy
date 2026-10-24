# ruff: noqa: F811
import io
from datetime import date, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.models import Gewerbe, Mahnung, Versand
from app.services import ablage
from app.services.mahnwesen import automatischer_mahnlauf, erstelle_mahnung, setze_automatik
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

SPAET = date.today() + timedelta(days=60)
HINWEIS = "maschinell erstellt"


def text_der_mahnung(mahnung) -> str:
    pdf = ablage.lies(mahnung.pdf_sha256)
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(pdf)).pages)


@pytest.fixture
def mit_app(app):
    with app.app_context():
        yield


def test_standardmaessig_aus(rechnung, admin, session, mit_app):  # noqa: F811
    assert session.get(Gewerbe, 1).auto_mahnen is False
    lauf = automatischer_mahnlauf(admin.id, heute=SPAET)
    assert (lauf.erstellt, lauf.verschickt) == (0, 0)
    assert session.execute(select(Mahnung)).first() is None


def test_eingeschaltet_erstellt_faellige_mahnung_mit_hinweis(rechnung, admin, session, mit_app):  # noqa: F811
    setze_automatik(True, admin.id)
    lauf = automatischer_mahnlauf(admin.id, heute=SPAET)
    assert lauf.erstellt == 1
    mahnung = session.execute(select(Mahnung)).scalar_one()
    assert mahnung.automatisch is True and mahnung.stufe == 1
    assert HINWEIS in text_der_mahnung(mahnung)
    # nächster Lauf am selben Tag erstellt nichts nochmal
    assert automatischer_mahnlauf(admin.id, heute=SPAET).erstellt == 0


def test_manuelle_mahnung_ohne_maschinen_hinweis(rechnung, admin, session, mit_app):  # noqa: F811
    mahnung = erstelle_mahnung(rechnung, admin.id, heute=SPAET)
    assert mahnung.automatisch is False
    assert HINWEIS not in text_der_mahnung(mahnung)


def test_mahnsperre_wird_nicht_gemahnt(rechnung, admin, session, mit_app):  # noqa: F811
    from app.services.mahnwesen import setze_mahnsperre

    setze_automatik(True, admin.id)
    setze_mahnsperre(rechnung, True, "Ratenzahlung", admin.id)
    assert automatischer_mahnlauf(admin.id, heute=SPAET).erstellt == 0


def test_versand_per_mail_wenn_moeglich(rechnung, admin, kunde, session, mit_app, monkeypatch):  # noqa: F811
    gesendet = []
    monkeypatch.setattr("app.services.mail.eingerichtet", lambda: True)
    monkeypatch.setattr("app.services.versand.sende", lambda **k: gesendet.append(k))
    kunde.email = "kunde@kunde.example"
    session.commit()
    setze_automatik(True, admin.id)
    lauf = automatischer_mahnlauf(admin.id, heute=SPAET)
    assert (lauf.erstellt, lauf.verschickt, lauf.nicht_verschickt) == (1, 1, [])
    assert gesendet[0]["an"] == "kunde@kunde.example"
    assert session.execute(select(Versand)).scalar_one().erfolgreich is True


def test_ohne_mail_liegt_die_mahnung_bereit(rechnung, admin, session, mit_app):  # noqa: F811
    setze_automatik(True, admin.id)
    lauf = automatischer_mahnlauf(admin.id, heute=SPAET)
    assert (lauf.erstellt, lauf.verschickt) == (1, 0) and len(lauf.nicht_verschickt) == 1
    assert session.execute(select(Mahnung)).scalar_one() is not None


def test_schalter_ueber_oberflaeche(angemeldet, session):
    seite = angemeldet.get("/einstellungen/mahnwesen").get_data(as_text=True)
    assert "Automatisch mahnen" in seite and "Standardmäßig ausgeschaltet" in seite
    assert 'name="auto_mahnen" value="y" checked' not in seite
    angemeldet.post("/einstellungen/mahnwesen/automatik", data={"auto_mahnen": "y"})
    assert session.get(Gewerbe, 1).auto_mahnen is True
    assert 'name="auto_mahnen" value="y" checked' in (
        angemeldet.get("/einstellungen/mahnwesen").get_data(as_text=True)
    )
    antwort = angemeldet.post(
        "/einstellungen/mahnwesen/automatik", headers={"X-Requested-With": "fetch"}
    )
    assert antwort.get_json() == {"auto_mahnen": False}
    assert session.get(Gewerbe, 1).auto_mahnen is False


def test_schalter_nur_mit_einstellungsrecht(client, admin, session):
    from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

    neuer_nutzer(session, "mitarbeiter@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "mitarbeiter@x.example", "passwort": ADMIN_PASSWORT})
    assert (
        client.post("/einstellungen/mahnwesen/automatik", data={"auto_mahnen": "y"}).status_code
        == 403
    )


def test_fehlgeschlagener_versand_wird_spaeter_nachgeholt(  # noqa: F811
    rechnung, admin, kunde, session, mit_app, monkeypatch
):
    from datetime import UTC, datetime

    from app.services.mail import MailFehler

    kunde.email = "kunde@kunde.example"
    session.commit()
    monkeypatch.setattr("app.services.mail.eingerichtet", lambda: True)

    def kaputt(**kwargs):
        raise MailFehler("Mailserver nicht erreichbar")

    monkeypatch.setattr("app.services.versand.sende", kaputt)
    setze_automatik(True, admin.id)
    erster = automatischer_mahnlauf(admin.id, heute=SPAET)
    assert (erster.erstellt, erster.verschickt, len(erster.nicht_verschickt)) == (1, 0, 1)
    mahnung = session.execute(select(Mahnung)).scalar_one()
    # Direkt danach wird nicht gleich wieder versucht (Sperre von sechs Stunden)
    assert automatischer_mahnlauf(admin.id, heute=SPAET).nicht_verschickt == []
    # Nach sieben Stunden klappt es nachträglich
    spaeter = datetime.now(UTC) + timedelta(hours=7)
    monkeypatch.setattr("app.services.mahnwesen._jetzt", lambda: spaeter)
    gesendet = []
    monkeypatch.setattr("app.services.versand.sende", lambda **k: gesendet.append(k))
    lauf = automatischer_mahnlauf(admin.id, heute=SPAET)
    assert (lauf.erstellt, lauf.verschickt) == (0, 1) and len(gesendet) == 1
    erfolgreiche = [
        v for v in session.execute(select(Versand)).scalars() if v.erfolgreich and v.mahnung_id
    ]
    assert [v.mahnung_id for v in erfolgreiche] == [mahnung.id]
    # und dann nicht noch einmal
    assert automatischer_mahnlauf(admin.id, heute=SPAET).verschickt == 0
