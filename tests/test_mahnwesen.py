import io
from datetime import date, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.domain.mahnung import LetzteMahnung, Stufe, faellige_stufe, naechste_stufe
from app.models import Mahnung, Protokoll
from app.services.mahnwesen import (
    MahnungNichtMoeglich,
    erstelle_mahnung,
    faellige_mahnungen,
    setze_mahnsperre,
)
from app.services.zahlungen import erfasse_zahlung
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()
STUFEN = [
    Stufe(1, "Zahlungserinnerung", 7, 7),
    Stufe(2, "1. Mahnung", 14, 7),
    Stufe(3, "2. Mahnung", 14, 7),
]
FAELLIG = date(2026, 3, 1)


# ---------- Domain ----------


@pytest.mark.parametrize(
    ("letzte", "heute", "erwartet"),
    [
        (None, FAELLIG + timedelta(days=6), None),
        (None, FAELLIG + timedelta(days=7), 1),
        (LetzteMahnung(1, date(2026, 3, 8)), date(2026, 3, 21), None),
        (LetzteMahnung(1, date(2026, 3, 8)), date(2026, 3, 22), 2),
        (LetzteMahnung(2, date(2026, 3, 22)), date(2026, 4, 5), 3),
        (LetzteMahnung(3, date(2026, 4, 5)), date(2027, 1, 1), None),
    ],
)
def test_faellige_stufe(letzte, heute, erwartet):
    stufe = faellige_stufe(faellig_am=FAELLIG, letzte=letzte, stufen=STUFEN, heute=heute)
    assert (stufe.nummer if stufe else None) == erwartet


def test_ohne_faelligkeit_keine_mahnung():
    assert faellige_stufe(faellig_am=None, letzte=None, stufen=STUFEN, heute=FAELLIG) is None


def test_naechste_stufe_unabhaengig_vom_datum():
    assert naechste_stufe(STUFEN, None).nummer == 1
    assert naechste_stufe(STUFEN, LetzteMahnung(2, FAELLIG)).nummer == 3
    assert naechste_stufe(STUFEN, LetzteMahnung(3, FAELLIG)) is None


# ---------- Service ----------


def nach_tagen(tage: int) -> date:
    return HEUTE + timedelta(days=tage)


def mahnen(rechnung, admin, app, heute):  # noqa: F811
    with app.app_context():
        return erstelle_mahnung(rechnung, admin.id, heute=heute)


def test_faellig_ab_tag_sieben_nach_faelligkeit(rechnung, admin):  # noqa: F811
    assert faellige_mahnungen(heute=nach_tagen(14 + 6)) == []
    faellig = faellige_mahnungen(heute=nach_tagen(14 + 7))
    assert [(r, s.nummer) for r, s in faellig] == [(rechnung, 1)]


def test_mahnlauf(rechnung, admin, app, session):  # noqa: F811
    erste = mahnen(rechnung, admin, app, nach_tagen(21))
    assert (erste.stufe, erste.bezeichnung, erste.offen_cent) == (1, "Zahlungserinnerung", 15220)
    assert erste.frist_bis == nach_tagen(28)
    assert faellige_mahnungen(heute=nach_tagen(34)) == []
    assert [s.nummer for _, s in faellige_mahnungen(heute=nach_tagen(35))] == [2]
    zweite = mahnen(rechnung, admin, app, nach_tagen(35))
    assert zweite.bezeichnung == "1. Mahnung"
    mahnen(rechnung, admin, app, nach_tagen(49))
    assert faellige_mahnungen(heute=nach_tagen(400)) == []
    with pytest.raises(MahnungNichtMoeglich, match="Alle Mahnstufen"):
        mahnen(rechnung, admin, app, nach_tagen(400))
    aktionen = session.execute(select(Protokoll.aktion)).scalars().all()
    assert aktionen.count("mahnung_erstellt") == 3


def test_offener_rest_nach_teilzahlung(rechnung, admin, app):  # noqa: F811
    erfasse_zahlung(
        rechnung,
        datum=HEUTE,
        betrag_cent=5000,
        zahlungsart="ueberweisung",
        angekommen_cent=None,
        notiz=None,
        nutzer_id=admin.id,
    )
    assert mahnen(rechnung, admin, app, nach_tagen(21)).offen_cent == 10220


def test_bezahlt_stoppt_mahnlauf(rechnung, admin, app):  # noqa: F811
    erfasse_zahlung(
        rechnung,
        datum=HEUTE,
        betrag_cent=15220,
        zahlungsart="bar",
        angekommen_cent=None,
        notiz=None,
        nutzer_id=admin.id,
    )
    assert faellige_mahnungen(heute=nach_tagen(100)) == []
    with pytest.raises(MahnungNichtMoeglich, match="nichts mehr offen"):
        mahnen(rechnung, admin, app, nach_tagen(100))


def test_mahnsperre_rechnung(rechnung, admin, app, session):  # noqa: F811
    setze_mahnsperre(rechnung, True, "Ratenzahlung vereinbart", admin.id)
    assert rechnung.mahnsperre and rechnung.mahnsperre_grund == "Ratenzahlung vereinbart"
    assert faellige_mahnungen(heute=nach_tagen(100)) == []
    with pytest.raises(MahnungNichtMoeglich, match="Mahnsperre"):
        mahnen(rechnung, admin, app, nach_tagen(100))
    setze_mahnsperre(rechnung, False, None, admin.id)
    assert faellige_mahnungen(heute=nach_tagen(100))


def test_mahnsperre_kontakt(rechnung, admin, kunde, session):  # noqa: F811
    kunde.mahnsperre = True
    session.commit()
    assert faellige_mahnungen(heute=nach_tagen(100)) == []


def test_mahnsperre_aendert_rechnung_sonst_nicht(rechnung, admin, session):  # noqa: F811
    setze_mahnsperre(rechnung, True, None, admin.id)  # Trigger erlaubt nur diese Spalten
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text("UPDATE rechnung SET summe_cent = 1, mahnsperre = false"))


def test_mahnung_unveraenderlich(rechnung, admin, app, session):  # noqa: F811
    mahnen(rechnung, admin, app, nach_tagen(21))
    for sql in ["UPDATE mahnung SET offen_cent = 1", "DELETE FROM mahnung"]:
        with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
            session.execute(text(sql))


def test_mahnung_pdf(rechnung, admin, app, angemeldet):  # noqa: F811
    mahnung = mahnen(rechnung, admin, app, nach_tagen(21))
    antwort = angemeldet.get(f"/rechnungen/{rechnung.id}/mahnungen/{mahnung.id}/pdf")
    assert antwort.mimetype == "application/pdf"
    inhalt = "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(antwort.data)).pages)
    for erwartet in [
        "Zahlungserinnerung",
        rechnung.nummer,
        "152,20 €",
        nach_tagen(28).strftime("%d.%m.%Y"),
        "Mit Banking-App scannen",
        "Café Sonnenschein",
    ]:
        assert erwartet in inhalt, erwartet


# ---------- Oberfläche ----------


def test_mahnung_ueber_oberflaeche(angemeldet, rechnung, session):  # noqa: F811
    antwort = angemeldet.post(f"/rechnungen/{rechnung.id}/mahnungen")
    assert antwort.status_code == 302
    assert session.execute(select(Mahnung.stufe)).scalar_one() == 1
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert "Zahlungserinnerung" in seite and "1. Mahnung erstellen" in seite


def test_mahnsperre_ueber_oberflaeche(angemeldet, rechnung):  # noqa: F811
    angemeldet.post(
        f"/rechnungen/{rechnung.id}/mahnsperre", data={"sperre": "y", "grund": "Stammkunde"}
    )
    assert rechnung.mahnsperre
    assert "Mahnsperre" in angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    angemeldet.post(f"/rechnungen/{rechnung.id}/mahnsperre", data={})
    assert not rechnung.mahnsperre


def test_kontakt_mahnsperre_im_formular(angemeldet, kunde):  # noqa: F811
    angemeldet.post(
        f"/kontakte/{kunde.id}/bearbeiten",
        data={
            "art": "firma",
            "firmenname": kunde.firmenname,
            "typ": "kunde",
            "land": "Deutschland",
            "mahnsperre": "y",
        },
    )
    assert kunde.mahnsperre


def test_zu_pruefen_zeigt_faellige_mahnung(angemeldet, rechnung, session):  # noqa: F811
    session.execute(text("ALTER TABLE rechnung DISABLE TRIGGER rechnung_schutz"))
    session.execute(
        text("UPDATE rechnung SET faellig_am = :d WHERE id = :i"),
        {"d": HEUTE - timedelta(days=10), "i": rechnung.id},
    )
    session.execute(text("ALTER TABLE rechnung ENABLE TRIGGER rechnung_schutz"))
    session.expire_all()
    seite = angemeldet.get("/zu-pruefen").get_data(as_text=True)
    assert "Mahnung fällig" in seite and "Zahlungserinnerung" in seite
    assert "1 Mahnung fällig" in angemeldet.get("/").get_data(as_text=True)


def test_mitarbeiter_darf_nicht_mahnen(client, rechnung, session):  # noqa: F811
    neuer_nutzer(session, "m@x.example", "mitarbeiter")
    client.post("/abmelden")
    client.post("/anmelden", data={"email": "m@x.example", "passwort": ADMIN_PASSWORT})
    assert client.post(f"/rechnungen/{rechnung.id}/mahnungen").status_code == 403
    assert (
        client.post(f"/rechnungen/{rechnung.id}/mahnsperre", data={"sperre": "y"}).status_code
        == 403
    )


# ---------- Einstellungen ----------


def test_mahnstufen_einstellen(angemeldet, session):
    daten = {}
    for n, (name, tage) in enumerate(
        [("Erinnerung", 3), ("Mahnung", 10), ("Letzte Mahnung", 10)], 1
    ):
        daten |= {
            f"stufe-{n}-bezeichnung": name,
            f"stufe-{n}-tage_nach": str(tage),
            f"stufe-{n}-frist_tage": "5",
            f"stufe-{n}-text": f"Text {n}",
        }
    assert angemeldet.post("/einstellungen/mahnwesen", data=daten).status_code == 302
    from app.models import Mahnstufe

    stufe = session.get(Mahnstufe, 1)
    assert (stufe.bezeichnung, stufe.tage_nach, stufe.frist_tage) == ("Erinnerung", 3, 5)
    daten["stufe-2-tage_nach"] = "-1"
    antwort = angemeldet.post("/einstellungen/mahnwesen", data=daten)
    assert antwort.status_code == 422


# ---------- Rückfrage bei zu früher Mahnung ----------


def test_faellig_ab_datum():
    from app.domain.mahnung import faellig_ab

    stufen = [Stufe(1, "Zahlungserinnerung", 7, 7), Stufe(2, "1. Mahnung", 14, 7)]
    faellig = date(2026, 9, 15)
    assert faellig_ab(faellig_am=faellig, letzte=None, stufe=stufen[0]) == date(2026, 9, 22)
    letzte = LetzteMahnung(1, date(2026, 10, 23))
    assert faellig_ab(faellig_am=faellig, letzte=letzte, stufe=stufen[1]) == date(2026, 11, 6)
    assert faellig_ab(faellig_am=None, letzte=None, stufe=stufen[0]) is None


def test_button_fragt_zurueck_wenn_noch_nicht_faellig(angemeldet, rechnung, admin, app):  # noqa: F811
    """Eine Mahnung vor Ablauf des Abstands ist erlaubt, aber nur nach Rückfrage."""
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert "erst ab dem" in seite and "Trotzdem erstellen?" in seite
    # Ist sie fällig, kommt keine Rückfrage
    spaeter = rechnung.faellig_am + timedelta(days=30)
    with app.app_context():
        erstelle_mahnung(rechnung, admin.id, heute=spaeter)  # Zahlungserinnerung am Tag X
    # Die nächste Stufe ist erst 14 Tage danach dran, also wieder mit Rückfrage
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert "1. Mahnung ist laut Zeitplan erst ab dem" in seite
