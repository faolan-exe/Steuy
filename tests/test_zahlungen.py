from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.domain.zahlung import (
    ZahlungUngueltig,
    ist_ueberfaellig,
    offene_gebuehr,
    status_nach_zahlungen,
)
from app.models import Protokoll, Zahlung
from app.services.rechnungen import neuer_entwurf
from app.services.zahlungen import (
    erfasse_zahlung,
    kennzahlen,
    storniere_zahlung,
    zu_pruefen,
)
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401

HEUTE = date.today()


@pytest.fixture
def rechnung(angemeldet, admin, kunde, bank, app):  # noqa: F811
    """Finalisierte Rechnung über 152,20 €, Rechnungsdatum heute, fällig in 14 Tagen."""
    from app.services.rechnungen import finalisiere

    entwurf = neuer_entwurf(admin.id)
    speichern(
        angemeldet, entwurf, kunde, rechnungsdatum=HEUTE.isoformat(), leistung_von=HEUTE.isoformat()
    )
    with app.app_context():
        return finalisiere(entwurf, admin.id)


def zahlen(rechnung, admin, betrag, **mehr):
    daten = {"datum": HEUTE, "zahlungsart": "ueberweisung", "angekommen_cent": None, "notiz": None}
    daten.update(mehr)
    return erfasse_zahlung(rechnung, betrag_cent=betrag, nutzer_id=admin.id, **daten)


# ---------- Domain ----------


@pytest.mark.parametrize(
    ("summe", "bezahlt", "status"),
    [
        (1000, 0, "offen"),
        (1000, 1, "teilbezahlt"),
        (1000, 999, "teilbezahlt"),
        (1000, 1000, "bezahlt"),
    ],
)
def test_status(summe, bezahlt, status):
    assert status_nach_zahlungen(summe, bezahlt) == status


def test_offene_gebuehr():
    assert offene_gebuehr(10000, None) == 0
    assert offene_gebuehr(10000, 9710) == 290


@pytest.mark.parametrize(
    ("faellig", "status", "erwartet"),
    [
        (HEUTE - timedelta(days=1), "offen", True),
        (HEUTE - timedelta(days=1), "teilbezahlt", True),
        (HEUTE, "offen", False),
        (HEUTE - timedelta(days=1), "bezahlt", False),
        (None, "offen", False),
    ],
)
def test_ueberfaellig(faellig, status, erwartet):
    assert ist_ueberfaellig(faellig, status, HEUTE) is erwartet


# ---------- Erfassen ----------


def test_vollzahlung(rechnung, admin, session):
    zahlen(rechnung, admin, 15220)
    assert rechnung.status == "bezahlt"
    assert rechnung.offen_cent == 0
    assert "zahlung_erfasst" in session.execute(select(Protokoll.aktion)).scalars().all()


def test_teilzahlungen(rechnung, admin):
    zahlen(rechnung, admin, 5000)
    assert (rechnung.status, rechnung.offen_cent) == ("teilbezahlt", 10220)
    zahlen(rechnung, admin, 10220, zahlungsart="bar")
    assert rechnung.status == "bezahlt"


@pytest.mark.parametrize(
    ("betrag", "mehr", "meldung"),
    [
        (15221, {}, "höher als der offene Rest"),
        (0, {}, "größer als 0"),
        (15220, {"angekommen_cent": 16000}, "Angekommen kann nicht mehr"),
        (15220, {"datum": HEUTE + timedelta(days=1)}, "Zukunft"),
    ],
)
def test_ungueltige_zahlung(rechnung, admin, betrag, mehr, meldung):
    with pytest.raises(ZahlungUngueltig, match=meldung):
        zahlen(rechnung, admin, betrag, **mehr)
    assert rechnung.status == "offen"


def test_keine_zahlung_zu_entwurf(admin, session):
    entwurf = neuer_entwurf(admin.id)
    with pytest.raises(ZahlungUngueltig, match="finalisiert"):
        zahlen(entwurf, admin, 100)


def test_rueckgaengig_per_gegenbuchung(rechnung, admin, session):
    zahlung = zahlen(rechnung, admin, 15220)
    storno = storniere_zahlung(zahlung, admin.id)
    assert storno.betrag_cent == -15220
    assert storno.datum == zahlung.datum
    assert rechnung.status == "offen"
    assert rechnung.offen_cent == 15220
    with pytest.raises(ZahlungUngueltig, match="bereits rückgängig"):
        storniere_zahlung(zahlung, admin.id)
    with pytest.raises(ZahlungUngueltig, match="Gegenbuchung"):
        storniere_zahlung(storno, admin.id)


@pytest.mark.parametrize(
    "sql",
    ["UPDATE zahlung SET betrag_cent = 1", "DELETE FROM zahlung"],
)
def test_zahlung_unveraenderlich(rechnung, admin, session, sql):
    zahlen(rechnung, admin, 100)
    with pytest.raises(DBAPIError, match="unveränderlich"), session.begin_nested():
        session.execute(text(sql))


def test_datenbank_nur_finalisierte_rechnung(admin, session):
    entwurf = neuer_entwurf(admin.id)
    with pytest.raises(DBAPIError, match="finalisierten"), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO zahlung (rechnung_id, datum, betrag_cent, zahlungsart, erfasst_von) "
                f"VALUES ({entwurf.id}, CURRENT_DATE, 100, 'bar', {admin.id})"
            )
        )


# ---------- Zu prüfen und Kennzahlen ----------


def test_zu_pruefen(rechnung, admin, session):
    entwurf = neuer_entwurf(admin.id)
    liste = zu_pruefen()
    assert rechnung in liste["offen"]
    assert entwurf in liste["entwuerfe"]
    assert liste["gebuehren"] == []

    zahlen(rechnung, admin, 15220, zahlungsart="paypal", angekommen_cent=14750)
    liste = zu_pruefen()
    assert rechnung not in liste["offen"]
    assert [z.rechnung for z in liste["gebuehren"]] == [rechnung]
    assert liste["anzahl"] == 2  # Entwurf + Gebühr


def test_ueberfaellige_zuerst(rechnung, admin, session):
    session.execute(text("ALTER TABLE rechnung DISABLE TRIGGER rechnung_schutz"))
    session.execute(
        text("UPDATE rechnung SET faellig_am = :d WHERE id = :i"),
        {"d": HEUTE - timedelta(days=3), "i": rechnung.id},
    )
    session.execute(text("ALTER TABLE rechnung ENABLE TRIGGER rechnung_schutz"))
    session.expire_all()
    assert zu_pruefen()["ueberfaellig"] == [rechnung]


def test_storno_hebt_gebuehr_auf(rechnung, admin):
    zahlung = zahlen(rechnung, admin, 15220, zahlungsart="paypal", angekommen_cent=14750)
    storniere_zahlung(zahlung, admin.id)
    assert zu_pruefen()["gebuehren"] == []


def test_kennzahlen_nach_zahlungsdatum(rechnung, admin):
    zahlen(rechnung, admin, 5000)
    werte = kennzahlen(HEUTE.year)
    assert werte["einnahmen_cent"] == 5000
    assert werte["offen_cent"] == 10220
    assert werte["einnahmen_monate"][HEUTE.month - 1] == 5000
    assert werte["anzahl_rechnungen"] == 1
    assert kennzahlen(HEUTE.year - 1)["einnahmen_cent"] == 0


# ---------- Oberfläche ----------


def test_zahlung_ueber_oberflaeche(angemeldet, rechnung, session):
    antwort = angemeldet.post(
        f"/rechnungen/{rechnung.id}/zahlungen",
        data={
            "datum": HEUTE.isoformat(),
            "betrag": "152,20",
            "zahlungsart": "paypal",
            "angekommen": "147,50",
        },
    )
    assert antwort.status_code == 302
    assert rechnung.status == "bezahlt"
    zahlung = session.execute(select(Zahlung)).scalar_one()
    assert zahlung.angekommen_cent == 14750
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert "PayPal" in seite and "4,70 €" in seite  # offene Gebühr


def test_zahlung_fehler_ueber_oberflaeche(angemeldet, rechnung):
    antwort = angemeldet.post(
        f"/rechnungen/{rechnung.id}/zahlungen",
        data={"datum": HEUTE.isoformat(), "betrag": "999,00", "zahlungsart": "bar"},
    )
    assert antwort.status_code == 422
    assert "höher als der offene Rest" in antwort.get_data(as_text=True)


def test_rueckgaengig_ueber_oberflaeche(angemeldet, rechnung, admin):
    zahlung = zahlen(rechnung, admin, 15220)
    antwort = angemeldet.post(f"/rechnungen/{rechnung.id}/zahlungen/{zahlung.id}/rueckgaengig")
    assert antwort.status_code == 302
    assert rechnung.status == "offen"


def test_zu_pruefen_seite_und_dashboard(angemeldet, rechnung, admin):
    neuer_entwurf(admin.id)
    seite = angemeldet.get("/zu-pruefen").get_data(as_text=True)
    assert rechnung.nummer in seite and "Entwurf" in seite
    start = angemeldet.get("/").get_data(as_text=True)
    assert "1 offene Rechnung" in start
    assert "152,20 €" in start  # offene Forderungen


def test_steuerberater_darf_nicht_zahlen(client, rechnung, session):
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    client.post("/abmelden")
    client.post("/anmelden", data={"email": "stb@x.example", "passwort": ADMIN_PASSWORT})
    antwort = client.post(
        f"/rechnungen/{rechnung.id}/zahlungen",
        data={"datum": HEUTE.isoformat(), "betrag": "152,20", "zahlungsart": "bar"},
    )
    assert antwort.status_code == 403
    assert client.get("/zu-pruefen").status_code == 200


def test_dashboard_vorjahr_und_grenzfarbe(angemeldet, rechnung, admin, session):  # noqa: F811
    from datetime import date as _date

    zahlen(rechnung, admin, 15220)
    start = angemeldet.get("/").get_data(as_text=True)
    # Das Vorjahr gibt es nur, wenn es dafür Daten gibt
    assert "Aktuelles Jahr" in start and f'value="{_date.today().year - 1}"' not in start
    assert "25.000,00 €" in start
    assert "fortschritt warnung" not in start
    vorjahr = angemeldet.get(f"/?jahr={_date.today().year - 1}").get_data(as_text=True)
    assert f"Zahlungseingänge {_date.today().year}: <strong>" in vorjahr
    # unbekannte Jahre fallen auf das aktuelle zurück
    assert "Zahlungseingänge 1999" not in angemeldet.get("/?jahr=1999").get_data(as_text=True)


def test_grenze_ueberschritten_gelb(angemeldet, admin, session):
    from app.models import Kategorie
    from app.services.buchungen import Buchungsdaten, festschreiben, lege_entwurf_an

    kategorie = session.execute(
        select(Kategorie).where(Kategorie.name == "Umsatzerlöse")
    ).scalar_one()
    buchung = lege_entwurf_an(
        Buchungsdaten(
            art="einnahme", belegdatum=HEUTE, betrag_cent=2_600_000, kategorie_id=kategorie.id
        ),
        admin.id,
    )
    festschreiben(buchung, admin.id, bezahlt_am=HEUTE, zahlungsart="ueberweisung")
    start = angemeldet.get("/").get_data(as_text=True)
    assert "fortschritt warnung" in start
    assert "voraussichtlich nicht mehr" in start


# ---------- Details, Nachweis, Sicherheitsabfrage ----------

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def test_zahlung_mit_referenz_und_nachweis(angemeldet, rechnung, session):
    import io

    antwort = angemeldet.post(
        f"/rechnungen/{rechnung.id}/zahlungen",
        data={
            "datum": HEUTE.isoformat(),
            "betrag": "152,20",
            "zahlungsart": "paypal",
            "referenz": " 7XK12345AB ",
            "notiz": "Kunde zahlt immer pünktlich",
            "nachweis": (io.BytesIO(PDF), "Kontoauszug März.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert antwort.status_code == 302
    zahlung = session.execute(select(Zahlung)).scalar_one()
    assert zahlung.referenz == "7XK12345AB"
    assert zahlung.nachweis_mime == "application/pdf"
    assert zahlung.nachweis_name == "Kontoauszug März.pdf"

    detail = angemeldet.get(f"/rechnungen/{rechnung.id}/zahlungen/{zahlung.id}")
    seite = detail.get_data(as_text=True)
    assert "7XK12345AB" in seite and "Kunde zahlt immer pünktlich" in seite
    assert "Kontoauszug März.pdf" in seite and "Rückgängig machen" in seite

    datei = angemeldet.get(f"/rechnungen/{rechnung.id}/zahlungen/{zahlung.id}/nachweis")
    assert datei.data == PDF and datei.mimetype == "application/pdf"
    assert "default-src 'none'" in datei.headers["Content-Security-Policy"]

    liste = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert f'/zahlungen/{zahlung.id}"' in liste and "Ref. 7XK12345AB" in liste


def test_nachweis_nur_pdf_und_bilder(angemeldet, rechnung, session):
    import io

    antwort = angemeldet.post(
        f"/rechnungen/{rechnung.id}/zahlungen",
        data={
            "datum": HEUTE.isoformat(),
            "betrag": "152,20",
            "zahlungsart": "bar",
            "nachweis": (io.BytesIO(b"<html>boese</html>"), "nachweis.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert antwort.status_code == 422
    assert "nur PDF, JPG und PNG" in antwort.get_data(as_text=True)
    assert session.execute(select(Zahlung)).first() is None


def test_ohne_nachweis_404(angemeldet, rechnung, admin):
    zahlung = zahlen(rechnung, admin, 15220)
    assert (
        angemeldet.get(f"/rechnungen/{rechnung.id}/zahlungen/{zahlung.id}/nachweis").status_code
        == 404
    )
    assert (
        angemeldet.get(f"/rechnungen/{rechnung.id + 1}/zahlungen/{zahlung.id}").status_code == 404
    )


def test_detail_nach_rueckgaengig(angemeldet, rechnung, admin):
    zahlung = zahlen(rechnung, admin, 15220)
    storno = storniere_zahlung(zahlung, admin.id)
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}/zahlungen/{zahlung.id}").get_data(
        as_text=True
    )
    assert "wurde rückgängig gemacht" in seite and "Rückgängig machen</button>" not in seite
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}/zahlungen/{storno.id}").get_data(
        as_text=True
    )
    assert "Gegenbuchung" in seite


def test_keine_blockierbare_confirm_abfrage(angemeldet, rechnung, admin):
    """confirm() wird in manchen Browsern still unterdrückt, dann passiert beim Klick nichts."""
    zahlen(rechnung, admin, 1000)
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert "confirm(" not in seite
    assert 'data-bestaetigen="Diese Zahlung rückgängig machen?' in seite
    assert "js/app.js" in seite
