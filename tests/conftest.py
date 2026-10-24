import pytest
from flask_migrate import upgrade
from sqlalchemy import text
from sqlalchemy.orm import scoped_session, sessionmaker

from app import create_app
from app.config import TestConfig
from app.extensions import db

FIRMENDATEN = {
    "name": "Musterwerkstatt",
    "inhaber": "Erika Mustermann",
    "strasse": "Hauptstraße 1",
    "plz": "12345",
    "ort": "Musterstadt",
    "email": "kontakt@musterwerkstatt.example",
    "telefon": "",
    "steuernummer": "12/345/67890",
    "ust_idnr": "",
}
ADMIN_EMAIL = "erika@musterwerkstatt.example"
ADMIN_PASSWORT = "ein-sicheres-passwort"


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """App gegen die Test-Datenbank. Das Schema entsteht nur über die Migrationen."""
    app = create_app(TestConfig)
    app.config["ABLAGE_VERZEICHNIS"] = str(tmp_path_factory.mktemp("ablage"))
    with app.app_context():
        with db.engine.begin() as verbindung:
            verbindung.execute(text("DROP SCHEMA public CASCADE"))
            verbindung.execute(text("CREATE SCHEMA public"))
        upgrade()
    # Kein dauerhaft aktiver App-Kontext: Jeder Request bekommt seinen eigenen (und eigenes `g`).
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def session(app):
    """Jeder Test läuft in einer Transaktion, die am Ende zurückgerollt wird (ADR 0002).

    Auch ein `commit()` im Code landet nur in einem Savepoint dieser Transaktion.
    """
    with app.app_context():
        verbindung = db.engine.connect()
    transaktion = verbindung.begin()
    original = db.session
    sitzung = scoped_session(
        sessionmaker(bind=verbindung, join_transaction_mode="create_savepoint")
    )
    # Flask-SQLAlchemy räumt die Session nach jedem Request ab. Im Test bleibt sie bis zum
    # Ende bestehen, damit Testobjekte nach einem Request weiter nutzbar sind.
    sitzung.remove = lambda: None
    db.session = sitzung
    yield sitzung
    scoped_session.remove(sitzung)
    db.session = original
    transaktion.rollback()
    verbindung.close()


@pytest.fixture
def client(app, session):
    return app.test_client()


@pytest.fixture
def admin(session):
    """Ein eingerichtetes Gewerbe mit Admin-Konto."""
    from app.services.einrichtung import richte_ein

    return richte_ein(dict(FIRMENDATEN), "Erika Mustermann", ADMIN_EMAIL, ADMIN_PASSWORT)


@pytest.fixture
def angemeldet(client, admin):
    antwort = client.post("/anmelden", data={"email": ADMIN_EMAIL, "passwort": ADMIN_PASSWORT})
    assert antwort.status_code == 302
    return client


def neuer_nutzer(session, email: str, rolle: str, passwort: str = ADMIN_PASSWORT, aktiv=True):
    from app.domain.passwort import hash_passwort
    from app.models import Nutzer

    nutzer = Nutzer(
        name=email,
        email=email,
        passwort_hash=hash_passwort(passwort),
        rolle=rolle,
        aktiv=aktiv,
    )
    session.add(nutzer)
    session.commit()
    return nutzer
