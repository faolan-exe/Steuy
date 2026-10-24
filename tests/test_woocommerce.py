# ruff: noqa: F811  (Fixtures werden importiert und als Parameter genutzt)
import copy
import io
import urllib.error
from datetime import date

import pytest
from sqlalchemy import select

from app.domain.woocommerce import BestellungUngueltig, lies_bestellung
from app.models import Gewerbe, Kontakt, Protokoll, Rechnung, ShopBestellung, Zahlung
from app.services import shop
from app.services.geheimnis import entschluessele
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_email import ausgang, mail_eingerichtet  # noqa: F401
from tests.test_rechnungen import bank  # noqa: F401

PAYPAL = {
    "id": 4711,
    "number": "1042",
    "status": "processing",
    "date_created": "2026-10-01T10:15:00",
    "date_paid": "2026-10-01T10:16:00",
    "payment_method": "ppcp-gateway",
    "transaction_id": "7XK12345AB",
    "total": "47.90",
    "total_tax": "0.00",
    "billing": {
        "first_name": "Lena",
        "last_name": "Schmidt",
        "company": "",
        "address_1": "Hauptstraße 5",
        "address_2": "",
        "city": "Leipzig",
        "postcode": "04109",
        "country": "DE",
        "email": "Lena@Example.de",
        "phone": "0341 123",
    },
    "line_items": [
        {
            "name": "Tasse „Morgen“",
            "quantity": 2,
            "total": "25.00",
            "sku": "T-01",
            "meta_data": [{"key": "pa_farbe", "display_key": "Farbe", "display_value": "Blau"}],
        },
        {"name": "Postkarte", "quantity": 3, "total": "10.00", "sku": "", "meta_data": []},
    ],
    "shipping_lines": [{"method_title": "DHL Paket", "total": "4.90"}],
    "fee_lines": [{"name": "Geschenkverpackung", "total": "8.00"}],
    "refunds": [],
}

VORKASSE = copy.deepcopy(PAYPAL) | {
    "id": 4712,
    "number": "1043",
    "status": "on-hold",
    "date_paid": None,
    "payment_method": "bacs",
    "transaction_id": "",
}


def bestellung(**aenderung):
    return copy.deepcopy(PAYPAL) | aenderung


@pytest.fixture
def verbunden(session, admin, app):
    from app.services.geheimnis import verschluessele

    gewerbe = session.get(Gewerbe, 1)
    gewerbe.shop_url = "https://shop.example.de"
    with app.app_context():
        gewerbe.shop_schluessel = verschluessele("ck_test")
        gewerbe.shop_geheimnis = verschluessele("cs_test")
    session.commit()
    return gewerbe


def abruf(app, admin, *bestellungen):
    with app.app_context():
        return shop.synchronisiere(admin.id, holer=lambda _seit: list(bestellungen))


# ---------- Domain ----------


def test_bestellung_lesen():
    b = lies_bestellung(PAYPAL)
    assert (b.externe_id, b.nummer, b.zahlungsart, b.summe_cent) == (4711, "1042", "paypal", 4790)
    assert b.bezahlt and b.bezahlt_am == date(2026, 10, 1) and b.braucht_rechnung
    assert b.kunde["email"] == "lena@example.de" and b.kunde["land"] == "Deutschland"
    tasse, karte, versand, verpackung = b.positionen
    assert (tasse.menge_tausendstel, tasse.einzelpreis_cent) == (2000, 1250)
    assert tasse.beschreibung == "Art.-Nr. T-01\nFarbe: Blau"
    # 10,00 € für 3 Stück geht nicht in Cent auf: Pauschale mit Mengenangabe
    assert (karte.menge_tausendstel, karte.einzelpreis_cent) == (1000, 1000)
    assert karte.beschreibung == "Menge: 3"
    assert versand.bezeichnung == "Versand (DHL Paket)" and versand.einzelpreis_cent == 490
    assert verpackung.einzelpreis_cent == 800
    assert b.hinweise == []


@pytest.mark.parametrize(
    ("status", "methode", "bezahlt", "erwartet"),
    [
        ("processing", "ppcp-gateway", "2026-10-01T10:00:00", True),
        ("pending", "ppcp-gateway", None, False),
        ("on-hold", "bacs", None, True),  # Vorkasse: Rechnung sofort
        ("on-hold", "cheque", None, False),
        ("cancelled", "bacs", None, False),
        ("failed", "stripe", None, False),
    ],
)
def test_wann_eine_rechnung_entsteht(status, methode, bezahlt, erwartet):
    b = lies_bestellung(bestellung(status=status, payment_method=methode, date_paid=bezahlt))
    assert b.braucht_rechnung is erwartet


def test_hinweise_bei_steuer_abweichung_und_erstattung():
    b = lies_bestellung(bestellung(total_tax="7.65", total="55.55"))
    assert any("Umsatzsteuer" in h for h in b.hinweise)
    b = lies_bestellung(bestellung(total="50.00"))
    assert any("nicht den Bestellbetrag" in h for h in b.hinweise)
    b = lies_bestellung(bestellung(refunds=[{"id": 1, "total": "-4.90"}]))
    assert b.erstattet_cent == 490 and any("4,90 €" in h for h in b.hinweise)


@pytest.mark.parametrize("betrag", ["12.345", "abc"])
def test_ungueltige_betraege(betrag):
    with pytest.raises(BestellungUngueltig):
        lies_bestellung(bestellung(total=betrag))


# ---------- Abruf ----------


def test_abruf_legt_kontakt_und_rechnungsentwurf_an(app, admin, verbunden, bank, session):
    ergebnis = abruf(app, admin, PAYPAL)
    assert (ergebnis.abgerufen, ergebnis.neue_rechnungen, ergebnis.zahlungen) == (1, 1, 0)
    eintrag = session.execute(select(ShopBestellung)).scalar_one()
    rechnung = eintrag.rechnung
    assert rechnung.status == "entwurf" and rechnung.summe_cent == 4790
    assert rechnung.rechnungsdatum == date(2026, 10, 1)
    assert rechnung.leistung_art == "lieferdatum" and rechnung.leistung_von == date(2026, 10, 1)
    assert "Bestellung 1042 vom 01.10.2026" in rechnung.einleitung
    assert rechnung.qr_ueberweisung is False  # schon bezahlt
    kontakt = session.execute(select(Kontakt)).scalar_one()
    assert kontakt.nachname == "Schmidt" and kontakt.ist_kunde and kontakt.kundennummer
    assert eintrag.rohdaten["transaction_id"] == "7XK12345AB"
    assert session.execute(select(Protokoll).where(Protokoll.aktion == "shop_abruf")).scalar_one()


def test_zweiter_abruf_erzeugt_nichts_doppelt(app, admin, verbunden, bank, session):
    abruf(app, admin, PAYPAL)
    ergebnis = abruf(app, admin, PAYPAL)
    assert ergebnis.neue_rechnungen == 0
    assert len(session.execute(select(Rechnung)).scalars().all()) == 1
    assert session.execute(select(ShopBestellung)).scalar_one().abrufe == 2


def test_offene_und_stornierte_bestellungen_werden_ignoriert(app, admin, verbunden, session):
    abruf(
        app,
        admin,
        bestellung(status="pending", date_paid=None),
        bestellung(id=9, status="cancelled", date_paid=None),
    )
    assert session.execute(select(ShopBestellung)).first() is None


def test_vorhandener_kontakt_per_email(app, admin, verbunden, bank, session):
    from app.services.kontakte import lege_kontakt_an

    vorhanden = lege_kontakt_an(
        {
            "art": "firma",
            "firmenname": "Schmidt Design",
            "typ": "lieferant",
            "email": "lena@example.de",
        },
        admin.id,
    )
    abruf(app, admin, PAYPAL)
    assert session.execute(select(Kontakt)).scalar_one() == vorhanden
    assert vorhanden.ist_kunde and vorhanden.kundennummer and vorhanden.lieferantennummer


def test_freigabe_finalisiert_versendet_und_uebernimmt_zahlung(
    angemeldet, app, admin, verbunden, bank, mail_eingerichtet, ausgang, session
):
    abruf(app, admin, PAYPAL)
    seite = angemeldet.get("/zu-pruefen").get_data(as_text=True)
    assert "#1042" in seite and "Freigeben" in seite
    eintrag = session.execute(select(ShopBestellung)).scalar_one()

    angemeldet.post(f"/shop/{eintrag.id}/freigeben")
    rechnung = eintrag.rechnung
    assert rechnung.nummer and rechnung.status == "bezahlt"
    zahlung = session.execute(select(Zahlung)).scalar_one()
    assert zahlung.datum == date(2026, 10, 1) and zahlung.zahlungsart == "paypal"
    assert zahlung.referenz == "7XK12345AB" and zahlung.betrag_cent == 4790
    (mail,) = ausgang
    assert mail["To"] == "lena@example.de"
    assert list(mail.iter_attachments())[0].get_content().startswith(b"%PDF")
    assert "#1042" not in angemeldet.get("/zu-pruefen").get_data(as_text=True)


def test_vorkasse_rechnung_mit_qr_und_spaeterer_zahlung(app, admin, verbunden, bank, session):
    abruf(app, admin, VORKASSE)
    eintrag = session.execute(select(ShopBestellung)).scalar_one()
    assert eintrag.rechnung.qr_ueberweisung is True and eintrag.bezahlt_am is None
    with app.app_context():
        shop.freigeben(eintrag, admin.id)
    assert eintrag.rechnung.status == "offen" and eintrag.zahlung_id is None

    bezahlt = copy.deepcopy(VORKASSE) | {"status": "processing", "date_paid": "2026-10-05T09:00:00"}
    ergebnis = abruf(app, admin, bezahlt)
    assert ergebnis.zahlungen == 1
    assert eintrag.rechnung.status == "bezahlt"
    assert session.get(Zahlung, eintrag.zahlung_id).datum == date(2026, 10, 5)
    # Kein zweites Mal
    assert abruf(app, admin, bezahlt).zahlungen == 0


def test_auto_modus(app, admin, verbunden, bank, mail_eingerichtet, ausgang, session):
    verbunden.shop_auto_versand = True
    session.commit()
    ergebnis = abruf(app, admin, PAYPAL, bestellung(id=5000, number="2000", total="1.00"))
    assert ergebnis.freigegeben == 1
    eintraege = {e.nummer: e for e in session.execute(select(ShopBestellung)).scalars()}
    assert eintraege["1042"].rechnung.status == "bezahlt"
    # Auffällige Bestellung wartet trotz Auto-Modus
    assert eintraege["2000"].rechnung.status == "entwurf"
    assert len(ausgang) == 1


def test_erstattung_als_hinweis(angemeldet, app, admin, verbunden, bank, session):
    abruf(app, admin, PAYPAL)
    eintrag = session.execute(select(ShopBestellung)).scalar_one()
    with app.app_context():
        shop.freigeben(eintrag, admin.id)
    erstattet = bestellung(status="completed", refunds=[{"id": 1, "total": "-4.90"}])
    assert abruf(app, admin, erstattet).hinweise == 1
    seite = angemeldet.get("/zu-pruefen").get_data(as_text=True)
    assert "4,90 € erstattet" in seite
    angemeldet.post(f"/shop/{eintrag.id}/erledigt")
    assert "4,90 € erstattet" not in angemeldet.get("/zu-pruefen").get_data(as_text=True)
    # Gleicher Stand erneut abgerufen: kein neuer Hinweis
    assert abruf(app, admin, erstattet).hinweise == 0


def test_seitenweiser_abruf(app, verbunden, monkeypatch):
    seiten = {1: [{"id": 1}, {"id": 2}], 2: [{"id": 3}]}
    aufrufe = []

    def anfrage(pfad, parameter):
        aufrufe.append(parameter)
        return seiten[parameter["page"]], {"X-WP-TotalPages": "2"}

    monkeypatch.setattr(shop, "_anfrage", anfrage)
    from datetime import UTC, datetime

    with app.app_context():
        ids = [b["id"] for b in shop.hole_bestellungen(datetime(2026, 10, 2, 12, tzinfo=UTC))]
    assert ids == [1, 2, 3]
    assert aufrufe[0]["modified_after"] == "2026-10-02T11:00:00"  # eine Stunde Überlappung


def test_falsche_schluessel(app, verbunden, monkeypatch):
    def abgelehnt(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://shop", 401, "Unauthorized", {}, io.BytesIO())

    monkeypatch.setattr("urllib.request.urlopen", abgelehnt)
    with app.app_context(), pytest.raises(shop.ShopFehler, match="Consumer Key"):
        shop.teste_verbindung()


# ---------- Einstellungen und Rechte ----------


def test_einstellungen_speichern(angemeldet, admin, session, app):
    antwort = angemeldet.post(
        "/einstellungen/shop",
        data={
            "shop_url": "https://mein-shop.de/",
            "shop_schluessel": "ck_abc",
            "shop_geheimnis": "cs_xyz",
            "shop_auto_versand": "y",
        },
    )
    assert antwort.status_code == 302
    gewerbe = session.get(Gewerbe, 1)
    assert gewerbe.shop_url == "https://mein-shop.de" and gewerbe.shop_auto_versand
    with app.app_context():
        assert entschluessele(gewerbe.shop_geheimnis) == "cs_xyz"
    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "shop_einstellungen")
    ).scalar_one()
    assert "cs_xyz" not in str(eintrag.details)
    seite = angemeldet.get("/einstellungen/shop").get_data(as_text=True)
    assert "verbunden" in seite and "cs_xyz" not in seite


def test_nur_https(angemeldet):
    seite = angemeldet.post(
        "/einstellungen/shop", data={"shop_url": "http://mein-shop.de"}
    ).get_data(as_text=True)
    assert "https://" in seite


def test_cli_ohne_shop(app, admin):
    ergebnis = app.test_cli_runner().invoke(args=["shop-abruf"])
    assert "Kein Shop verbunden" in ergebnis.output


@pytest.mark.parametrize(("rolle", "status"), [("mitarbeiter", 403), ("buchhalter", 302)])
def test_rechte(client, app, admin, verbunden, bank, session, rolle, status):
    abruf(app, admin, PAYPAL)
    eintrag = session.execute(select(ShopBestellung)).scalar_one()
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.post(f"/shop/{eintrag.id}/freigeben").status_code == status
    assert client.get("/einstellungen/shop").status_code == 403
