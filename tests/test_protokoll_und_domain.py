import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.domain.kleinunternehmer import Grenze, KeineGrenzeHinterlegt, grenze_fuer_jahr
from app.domain.passwort import (
    PasswortZuKurz,
    hash_passwort,
    normalisiere_email,
    pruefe_passwort,
)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE protokoll SET aktion = 'manipuliert'",
        "DELETE FROM protokoll",
        "TRUNCATE protokoll",
    ],
)
def test_protokoll_unveraenderlich_auch_per_sql(admin, session, sql):
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text(sql))


def test_nutzer_mit_protokoll_nicht_loeschbar(admin, session):
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(text("DELETE FROM nutzer"))


def test_ungueltige_rolle_abgelehnt(admin, session):
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(text("UPDATE nutzer SET rolle = 'chef'"))


def test_passwort():
    h = hash_passwort("richtig-lang-genug")
    assert pruefe_passwort(h, "richtig-lang-genug")
    assert not pruefe_passwort(h, "falsch-aber-lang")
    assert not pruefe_passwort(None, "richtig-lang-genug")
    assert not pruefe_passwort("kein-hash", "richtig-lang-genug")


def test_passwort_mindestlaenge():
    with pytest.raises(PasswortZuKurz):
        hash_passwort("123456789")


def test_normalisiere_email():
    assert normalisiere_email("  Max@Beispiel.DE ") == "max@beispiel.de"


GRENZEN = [Grenze(2025, 2_500_000, 10_000_000), Grenze(2020, 2_200_000, 5_000_000)]


@pytest.mark.parametrize(
    ("jahr", "ab"),
    [(2020, 2020), (2024, 2020), (2025, 2025), (2031, 2025)],
)
def test_grenze_fuer_jahr(jahr, ab):
    assert grenze_fuer_jahr(GRENZEN, jahr).gueltig_ab_jahr == ab


def test_keine_grenze_hinterlegt():
    with pytest.raises(KeineGrenzeHinterlegt):
        grenze_fuer_jahr(GRENZEN, 2019)
