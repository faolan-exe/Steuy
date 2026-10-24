import io
import re
from datetime import date

import pytest
from pypdf import PdfReader
from sqlalchemy import select, text

from app.domain.euer import OHNE_ZUORDNUNG, Posten, Zeile, verteile
from app.models import Kategorie
from app.services.buchungen import (
    Buchungsdaten,
    erfasse_gebuehren,
    festschreiben,
    lege_entwurf_an,
    storniere,
)
from app.services.euer import berechne, vordruck_jahr
from app.services.zahlungen import erfasse_zahlung
from tests.conftest import ADMIN_PASSWORT, neuer_nutzer
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401

HEUTE = date.today()


def kategorie_id(session, name):
    return session.execute(select(Kategorie.id).where(Kategorie.name == name)).scalar_one()


def ausgabe(session, admin, name, betrag, prozent=100, datum=HEUTE, art="ausgabe"):
    buchung = lege_entwurf_an(
        Buchungsdaten(
            art=art,
            belegdatum=datum,
            betrag_cent=betrag,
            kategorie_id=kategorie_id(session, name),
            betrieblich_prozent=prozent,
            partner=f"Lieferant {name}",
        ),
        admin.id,
    )
    return festschreiben(buchung, admin.id, bezahlt_am=datum, zahlungsart="ueberweisung")


def zahlen(rechnung, admin, betrag, **mehr):  # noqa: F811
    daten = {"datum": HEUTE, "zahlungsart": "ueberweisung", "angekommen_cent": None, "notiz": None}
    daten.update(mehr)
    return erfasse_zahlung(rechnung, betrag_cent=betrag, nutzer_id=admin.id, **daten)


def kz(ergebnis, kennzahl):
    """Wie zeile(), aber über die Kennzahl: bleibt gleich, wenn sich die Zeilennummern
    mit einem neuen Vordruck verschieben."""
    for z, betrag, posten in ergebnis.einnahmen + ergebnis.ausgaben:
        if z.kennzahl == kennzahl:
            return betrag, posten
    return None, []


def zeile(ergebnis, nummer):
    for z, betrag, posten in ergebnis.einnahmen + ergebnis.ausgaben:
        if z.nummer == nummer:
            return betrag, posten
    return None, []


# ---------- Domain ----------


def test_verteile_summen_und_reihenfolge():
    zeilen = [
        Zeile(12, "111", "Kleinunternehmer", "einnahme"),
        Zeile(51, "229", "Arbeitsmittel", "ausgabe"),
    ]
    posten = [
        Posten(51, "ausgabe", date(2025, 3, 1), "Papier", 1000),
        Posten(12, "einnahme", date(2025, 2, 1), "RE1", 50000),
        Posten(OHNE_ZUORDNUNG["ausgabe"], "ausgabe", date(2025, 4, 1), "Unbekannt", 500),
        Posten(51, "ausgabe", date(2025, 1, 1), "Toner", 2000),
    ]
    e = verteile(2025, 2025, zeilen, posten)
    assert [z.nummer for z, _, _ in e.ausgaben] == [51, 0]
    assert e.summe_einnahmen == 50000 and e.summe_ausgaben == 3500 and e.gewinn == 46500
    assert [p.text for p in e.ausgaben[0][2]] == ["Toner", "Papier"]
    assert any("keine Zeile" in h for h in e.hinweise)


def test_hinweis_fremdes_vordruckjahr():
    e = verteile(2026, 2025, [], [])
    assert any("Vordruck 2025" in h and "2026" in h for h in e.hinweise)
    assert e.gewinn == 0


# ---------- Service ----------


def test_vordruck_jahr(admin):
    assert vordruck_jahr(2025) == 2025
    assert vordruck_jahr(2026) == 2026
    assert vordruck_jahr(2027) == 2026  # neuester bekannter Vordruck
    assert vordruck_jahr(2020) == 2025  # ältere Jahre: frühester bekannter


def test_rechnung_und_ausgaben(rechnung, admin, session):  # noqa: F811
    zahlen(rechnung, admin, 15220)
    ausgabe(session, admin, "Software und Abos", 4990)
    ausgabe(session, admin, "Telefon und Internet", 4000, prozent=50)
    ausgabe(session, admin, "Büromaterial", 1250)
    e = berechne(HEUTE.year)
    assert kz(e, "111")[0] == 15220
    assert kz(e, "228")[0] == 4990
    assert kz(e, "280")[0] == 2000  # nur betrieblicher Anteil
    assert kz(e, "229")[0] == 1250
    assert e.summe_einnahmen == 15220 and e.summe_ausgaben == 8240 and e.gewinn == 6980
    texte = [p.text for p in kz(e, "280")[1]]
    assert texte == ["Lieferant Telefon und Internet (50 % betrieblich)"]


def test_zuflussprinzip_jahr_der_zahlung(rechnung, admin, session):  # noqa: F811
    buchung = lege_entwurf_an(
        Buchungsdaten(
            art="ausgabe",
            belegdatum=date(HEUTE.year - 1, 12, 28),
            betrag_cent=10000,
            kategorie_id=kategorie_id(session, "Werbung"),
        ),
        admin.id,
    )
    festschreiben(buchung, admin.id, bezahlt_am=date(HEUTE.year, 1, 3), zahlungsart="ueberweisung")
    assert kz(berechne(HEUTE.year), "224")[0] == 10000
    assert berechne(HEUTE.year - 1).summe_ausgaben == 0


def test_storno_hebt_auf(session, admin):
    buchung = ausgabe(session, admin, "Fortbildung", 29900)
    storniere(buchung, admin.id)
    e = berechne(HEUTE.year)
    assert kz(e, "281")[0] == 0
    assert len(kz(e, "281")[1]) == 2


def test_gebuehren_in_uebrigen_ausgaben(rechnung, admin, session):  # noqa: F811
    z = zahlen(rechnung, admin, 15220, zahlungsart="paypal", angekommen_cent=14750)
    erfasse_gebuehren([z.id], admin.id)
    e = berechne(HEUTE.year)
    assert kz(e, "183")[0] == 470
    assert e.gewinn == 15220 - 470


def test_einnahme_ohne_rechnung_in_zeile_12(session, admin):
    ausgabe(session, admin, "Umsatzerlöse", 3000, art="einnahme")
    assert kz(berechne(HEUTE.year), "111")[0] == 3000


def test_kategorie_ohne_zuordnung(session, admin):
    neue = Kategorie(name="Exotisch", art="ausgabe", sortierung=99)
    session.add(neue)
    session.commit()
    ausgabe(session, admin, "Exotisch", 777)
    e = berechne(HEUTE.year)
    assert zeile(e, OHNE_ZUORDNUNG["ausgabe"])[0] == 777
    assert e.summe_ausgaben == 777
    assert any("keine Zeile" in h for h in e.hinweise)


def test_zuordnung_2025_aus_vordruck(admin, session):
    """Stichproben gegen den amtlichen Vordruck 2025 (BMF-Schreiben vom 29.08.2025)."""
    erwartet = {
        None: (12, "111"),
        "Waren und Material": (27, "100"),
        "Fremdleistungen": (29, "110"),
        "Geringwertige Anschaffungen": (36, "132"),
        "Reisekosten": (44, "221"),
        "Fortbildung": (45, "281"),
        "Werbung": (54, "224"),
        "Sonstige Ausgaben": (60, "183"),
    }
    zeilen = session.execute(
        text(
            "SELECT k.name, z.zeile, e.kennzahl FROM euer_zuordnung z "
            "LEFT JOIN kategorie k ON k.id = z.kategorie_id "
            "JOIN euer_zeile e ON e.steuerjahr = z.steuerjahr AND e.zeile = z.zeile "
            "WHERE z.steuerjahr = 2025"
        )
    ).all()
    tatsaechlich = {name: (zeile, kz) for name, zeile, kz in zeilen}
    for name, wert in erwartet.items():
        assert tatsaechlich[name] == wert, name
    # Jede aktive Kategorie hat 2025 eine Zeile
    namen = set(session.execute(select(Kategorie.name)).scalars())
    assert namen <= set(tatsaechlich)


def test_rechnungszuordnung_nur_einmal(admin, session):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(
            text(
                "INSERT INTO euer_zuordnung (steuerjahr, kategorie_id, zeile) "
                "VALUES (2025, NULL, 60)"
            )
        )


# ---------- Oberfläche ----------


def test_seite_csv_pdf(angemeldet, rechnung, admin, session):  # noqa: F811
    zahlen(rechnung, admin, 15220)
    ausgabe(session, admin, "Software und Abos", 4990)
    seite = angemeldet.get(f"/auswertung?jahr={HEUTE.year}").get_data(as_text=True)
    assert "152,20 €" in seite and "49,90 €" in seite and "102,30 €" in seite
    assert "Laufende EDV-Kosten" in seite

    csv = angemeldet.get(f"/auswertung/euer.csv?jahr={HEUTE.year}").get_data(as_text=True)
    assert csv.startswith("﻿Anlage EÜR;")
    assert "12;111;Betriebseinnahmen als umsatzsteuerlicher Kleinunternehmer" in csv
    assert ";;Gewinn/Verlust;102,30" in csv

    pdf = angemeldet.get(f"/auswertung/euer.pdf?jahr={HEUTE.year}")
    text_ = "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(pdf.data)).pages)
    assert f"Einnahmen-Überschuss-Rechnung {HEUTE.year}" in text_
    assert "102,30 €" in text_


def test_leeres_jahr(angemeldet):
    seite = angemeldet.get("/auswertung?jahr=2025").get_data(as_text=True)
    assert "Keine Posten" in seite


@pytest.mark.parametrize(("rolle", "status"), [("mitarbeiter", 403), ("steuerberater", 200)])
def test_rechte(client, admin, session, rolle, status):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/auswertung").status_code == status
    assert client.get("/auswertung/euer.csv").status_code == status


def test_zuordnung_2026_aus_vordruck(admin, session):
    """Stichproben gegen den amtlichen Vordruck 2026 (BMF-Schreiben vom 01.09.2026).
    Ab „Waren“ liegen die Ausgaben eine Zeile tiefer als 2025."""
    erwartet = {
        None: (12, "111"),
        "Waren und Material": (29, "100"),
        "Fremdleistungen": (30, "110"),
        "Geringwertige Anschaffungen": (37, "132"),
        "Miete und Raumkosten": (40, "150"),
        "Reisekosten": (45, "221"),
        "Werbung": (55, "224"),
        "Sonstige Ausgaben": (61, "183"),
        "Fahrzeugkosten": (71, "146"),
    }
    zeilen = session.execute(
        text(
            "SELECT k.name, z.zeile, e.kennzahl FROM euer_zuordnung z "
            "LEFT JOIN kategorie k ON k.id = z.kategorie_id "
            "JOIN euer_zeile e ON e.steuerjahr = z.steuerjahr AND e.zeile = z.zeile "
            "WHERE z.steuerjahr = 2026"
        )
    ).all()
    tatsaechlich = {name: (zeile, kz_) for name, zeile, kz_ in zeilen}
    for name, wert in erwartet.items():
        assert tatsaechlich[name] == wert, name
    namen = set(session.execute(select(Kategorie.name)).scalars())
    assert namen <= set(tatsaechlich)
    afa = dict(
        session.execute(
            text(
                "SELECT kennzahl, zeile FROM euer_zeile "
                "WHERE steuerjahr = 2026 AND kennzahl IN ('130', '131')"
            )
        ).all()
    )
    assert afa == {"131": 33, "130": 34}


def test_gleiche_kennzahlen_2025_und_2026(admin, session):
    """Nur die Zeilennummern ändern sich, die Kennzahlen je Kategorie bleiben gleich."""

    def kennzahlen(jahr):
        return dict(
            session.execute(
                text(
                    "SELECT coalesce(k.name, '(Rechnungen)'), e.kennzahl FROM euer_zuordnung z "
                    "LEFT JOIN kategorie k ON k.id = z.kategorie_id "
                    "JOIN euer_zeile e ON e.steuerjahr = z.steuerjahr AND e.zeile = z.zeile "
                    "WHERE z.steuerjahr = :j"
                ),
                {"j": jahr},
            ).all()
        )

    assert kennzahlen(2026) == kennzahlen(2025)


# ---------- Summenzeilen je Vordruckjahr ----------


@pytest.mark.parametrize(
    ("jahr", "ausgaben", "gewinn"),
    [
        (2025, "Zeile 75, Kz 199", "Zeile 76 abzüglich Zeile 77"),
        (2026, "Zeile 76, Kz 199", "Zeile 77 abzüglich Zeile 78"),
    ],
)
def test_summenzeilen_stimmen_zum_vordruck(angemeldet, jahr, ausgaben, gewinn):
    """Im Vordruck 2026 liegen die Ausgaben-Summe und die Gewinnzeilen eine Zeile tiefer."""
    seite = angemeldet.get(f"/auswertung?jahr={jahr}").get_data(as_text=True)
    assert "Summe Betriebseinnahmen (Zeile 23, Kz 159)" in seite
    assert f"Summe Betriebsausgaben ({ausgaben})" in seite
    assert f"({gewinn})" in seite


def test_summenzeilen_im_pdf(angemeldet, rechnung, admin):  # noqa: F811
    zahlen(rechnung, admin, 15220)
    text_ = "\n".join(
        s.extract_text()
        for s in PdfReader(
            io.BytesIO(angemeldet.get(f"/auswertung/euer.pdf?jahr={HEUTE.year}").data)
        ).pages
    )
    erwartet = "Zeile 76" if HEUTE.year >= 2026 else "Zeile 75"
    assert f"Summe Betriebsausgaben ({erwartet})" in text_
    # Abschnitt „Ermittlung des Gewinns“: Übertragszeilen 77/78 (2026) bzw. 76/77 (2025)
    uebertrag = ("77", "78") if HEUTE.year >= 2026 else ("76", "77")
    assert re.search(rf"{uebertrag[0]}\s+Summe der Betriebseinnahmen", text_)
    assert re.search(rf"{uebertrag[1]}\s+abzüglich Summe der Betriebsausgaben", text_)


def test_summenzeilen_modell(admin, session):
    from app.models import EuerSummen

    s26 = session.get(EuerSummen, 2026)
    assert (s26.ausgaben_zeile, s26.gewinn_einnahmen_zeile, s26.gewinn_ausgaben_zeile) == (
        76,
        77,
        78,
    )
    assert session.get(EuerSummen, 2025).ausgaben_zeile == 75


def test_ohne_vordruck_keine_erfundenen_zeilennummern(angemeldet, session):
    from sqlalchemy import text

    session.execute(text("DELETE FROM euer_summen"))
    session.execute(text("DELETE FROM euer_zuordnung"))
    session.execute(text("DELETE FROM euer_zeile"))
    session.commit()
    seite = angemeldet.get("/auswertung?jahr=2026").get_data(as_text=True)
    assert "Summe Betriebsausgaben" in seite and "Zeile 7" not in seite
