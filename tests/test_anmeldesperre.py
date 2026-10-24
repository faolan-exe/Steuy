from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.domain.sperre import gesperrt
from app.models import Anmeldeversuch
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT

JETZT = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def test_regel():
    vier = [JETZT - timedelta(minutes=i) for i in range(4)]
    assert not gesperrt(vier, [], JETZT)
    assert gesperrt(vier + [JETZT], [], JETZT)
    alt = [JETZT - timedelta(minutes=16)] * 10
    assert not gesperrt(alt, alt, JETZT)
    assert gesperrt([], [JETZT] * 20, JETZT)


def anmelden(client, email=ADMIN_EMAIL, passwort=ADMIN_PASSWORT, ip="10.0.0.1"):
    return client.post(
        "/anmelden",
        data={"email": email, "passwort": passwort},
        environ_base={"REMOTE_ADDR": ip},
    )


def test_fuenf_fehlversuche_sperren_konto(client, admin):
    for _ in range(5):
        assert anmelden(client, passwort="falsch-falsch").status_code == 200
    antwort = anmelden(client)  # jetzt sogar mit richtigem Passwort
    assert antwort.status_code == 429
    assert "Zu viele Anmeldeversuche" in antwort.get_data(as_text=True)
    # anderes Konto ist nicht betroffen
    assert anmelden(client, email="jemand@x.example").status_code == 200


def test_sperre_endet_nach_15_minuten(client, admin, session):
    for _ in range(5):
        anmelden(client, passwort="falsch-falsch")
    session.execute(
        update(Anmeldeversuch).values(zeitpunkt=Anmeldeversuch.zeitpunkt - timedelta(minutes=16))
    )
    session.commit()
    assert anmelden(client).status_code == 302


def test_erfolg_setzt_zaehler_zurueck(client, admin):
    for _ in range(4):
        anmelden(client, passwort="falsch-falsch")
    assert anmelden(client).status_code == 302
    client.post("/abmelden")
    for _ in range(4):
        anmelden(client, passwort="falsch-falsch")
    assert anmelden(client).status_code == 302


def test_sperre_je_adresse(client, admin):
    for i in range(20):
        anmelden(client, email=f"raten{i}@x.example", ip="203.0.113.9")
    assert anmelden(client, ip="203.0.113.9").status_code == 429
    assert anmelden(client, ip="198.51.100.1").status_code == 302


def test_keine_klartextdaten(client, admin, session):
    anmelden(client, passwort="falsch-falsch", ip="192.0.2.55")
    versuch = session.execute(select(Anmeldeversuch)).scalar_one()
    assert ADMIN_EMAIL not in versuch.email_hash
    assert "192.0.2.55" not in versuch.ip_hash
    assert len(versuch.email_hash) == 64


def test_alte_eintraege_werden_geloescht(client, admin, session):
    anmelden(client, passwort="falsch-falsch")
    session.execute(update(Anmeldeversuch).values(zeitpunkt=JETZT - timedelta(days=30)))
    session.commit()
    anmelden(client, passwort="falsch-falsch")
    assert len(session.execute(select(Anmeldeversuch)).all()) == 1
