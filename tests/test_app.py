import pytest
from sqlalchemy import text

from app import create_app
from app.config import Config


def test_startseite_angemeldet(angemeldet):
    antwort = angemeldet.get("/")
    assert antwort.status_code == 200
    seite = antwort.get_data(as_text=True)
    assert "Dashboard" in seite
    assert "Musterwerkstatt" in seite


def test_gesund_ohne_anmeldung(client):
    antwort = client.get("/gesund")
    assert antwort.status_code == 200
    assert antwort.get_json() == {"status": "ok", "datenbank": "ok"}


def test_ohne_secret_key_startet_die_app_nicht():
    class OhneSchluessel(Config):
        SECRET_KEY = None

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(OhneSchluessel)


def test_euro_filter_im_template(app):
    with app.app_context():
        vorlage = app.jinja_env.from_string("{{ 123456 | euro }}")
        assert vorlage.render() == "1.234,56 €"


def test_migrationen_angewendet(session):
    version = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version


def test_rollback_zwischen_tests_teil_1(session):
    session.execute(text("CREATE TABLE rollback_probe (id int)"))
    session.commit()


def test_rollback_zwischen_tests_teil_2(session):
    vorhanden = session.execute(text("SELECT to_regclass('rollback_probe')")).scalar_one()
    assert vorhanden is None
