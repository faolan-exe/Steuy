from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.domain.rollen import (
    EINSTELLBAR,
    NUR_ADMIN,
    STANDARDRECHTE,
    Recht,
    Rolle,
    hat_recht,
)
from app.models import Nutzer, Protokoll
from app.services.nutzerverwaltung import (
    EmailVergeben,
    LetzterAdmin,
    aendere_nutzer,
    lege_nutzer_an,
)
from app.services.rechte import UngueltigesRecht, darf, rechte_matrix, setze_rechte
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORT, neuer_nutzer

# Erwartung direkt aus der Tabelle in docs/domain/rollen.md
ERWARTET = {
    Recht.ANSEHEN: "AAAA",
    Recht.BELEGE: "AAA-",
    Recht.STAMMDATEN: "AAA-",
    Recht.ENTWUERFE: "AAA-",
    Recht.RECHNUNGEN_VERSENDEN: "AA--",
    Recht.ZAHLUNGEN: "AA--",
    Recht.BUCHEN: "AA--",
    Recht.AUSWERTUNGEN: "AA-A",
    Recht.EXPORT: "AA-A",
    Recht.PROTOKOLL: "AA-A",
    Recht.EINSTELLUNGEN: "A---",
    Recht.NUTZER_VERWALTEN: "A---",
    Recht.JAHR_ABSCHLIESSEN: "A---",
}
REIHENFOLGE = [Rolle.ADMIN, Rolle.BUCHHALTER, Rolle.MITARBEITER, Rolle.STEUERBERATER]


@pytest.mark.parametrize("recht", list(Recht))
@pytest.mark.parametrize("rolle", REIHENFOLGE)
def test_standardrechte_wie_dokumentiert(admin, session, rolle, recht):
    nutzer = admin if rolle == Rolle.ADMIN else neuer_nutzer(session, f"{rolle}@x.example", rolle)
    erwartet = ERWARTET[recht][REIHENFOLGE.index(rolle)] == "A"
    assert darf(nutzer, recht) is erwartet


def test_domain_und_migration_stimmen_ueberein(admin):
    assert rechte_matrix() == {rolle: set(rechte) for rolle, rechte in STANDARDRECHTE.items()}


def test_nur_admin_rechte_nie_fuer_andere():
    for recht in NUR_ADMIN:
        assert not hat_recht(Rolle.BUCHHALTER, recht, set(Recht))


def test_deaktivierter_nutzer_darf_nichts(admin, session):
    nutzer = neuer_nutzer(session, "weg@x.example", "buchhalter", aktiv=False)
    assert not darf(nutzer, Recht.ANSEHEN)


def test_rechte_aendern_mit_protokoll(admin, session):
    matrix = rechte_matrix()
    matrix[Rolle.MITARBEITER] = matrix[Rolle.MITARBEITER] | {Recht.ZAHLUNGEN}
    matrix[Rolle.STEUERBERATER] = matrix[Rolle.STEUERBERATER] - {Recht.EXPORT}
    setze_rechte(matrix, admin.id)

    mitarbeiter = neuer_nutzer(session, "m@x.example", "mitarbeiter")
    steuerberater = neuer_nutzer(session, "s@x.example", "steuerberater")
    assert darf(mitarbeiter, Recht.ZAHLUNGEN)
    assert not darf(steuerberater, Recht.EXPORT)

    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "rechte_geaendert")
    ).scalar_one()
    assert eintrag.details == {
        "mitarbeiter": {"hinzugefuegt": ["zahlungen"], "entfernt": []},
        "steuerberater": {"hinzugefuegt": [], "entfernt": ["export"]},
    }


@pytest.mark.parametrize("recht", sorted(NUR_ADMIN))
def test_nur_admin_rechte_nicht_vergebbar(admin, recht):
    matrix = rechte_matrix()
    matrix[Rolle.BUCHHALTER] = matrix[Rolle.BUCHHALTER] | {recht}
    with pytest.raises(UngueltigesRecht):
        setze_rechte(matrix, admin.id)


def test_nutzer_anlegen_und_anmelden(client, admin, session):
    lege_nutzer_an("Bea Buch", "Bea@X.example ", "buchhalter", "passwort-fuer-bea", None, admin.id)
    antwort = client.post(
        "/anmelden", data={"email": "bea@x.example", "passwort": "passwort-fuer-bea"}
    )
    assert antwort.status_code == 302
    aktionen = session.execute(select(Protokoll.aktion)).scalars().all()
    assert "nutzer_angelegt" in aktionen


def test_email_nur_einmal(admin):
    with pytest.raises(EmailVergeben):
        lege_nutzer_an("Doppelt", ADMIN_EMAIL, "mitarbeiter", "irgendwas-langes", None, admin.id)


def test_letzter_admin_bleibt(admin):
    with pytest.raises(LetzterAdmin):
        aendere_nutzer(admin, rolle="buchhalter", admin_id=admin.id)
    with pytest.raises(LetzterAdmin):
        aendere_nutzer(admin, aktiv=False, admin_id=admin.id)
    with pytest.raises(LetzterAdmin):
        aendere_nutzer(admin, zugang_bis=date.today() - timedelta(days=1), admin_id=admin.id)


def test_mit_zweitem_admin_darf_herabgestuft_werden(admin, session):
    neuer_nutzer(session, "zweiter@x.example", "admin")
    aendere_nutzer(admin, rolle="buchhalter", admin_id=admin.id)
    assert admin.rolle == "buchhalter"


def test_aenderung_protokolliert_ohne_passwort(admin, session):
    nutzer = neuer_nutzer(session, "m@x.example", "mitarbeiter")
    aendere_nutzer(
        nutzer, rolle="buchhalter", neues_passwort="ganz-neues-passwort", admin_id=admin.id
    )
    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "nutzer_geaendert")
    ).scalar_one()
    assert eintrag.details == {
        "rolle": {"alt": "mitarbeiter", "neu": "buchhalter"},
        "passwort": "neu gesetzt",
    }


def test_befristeter_zugang(client, admin, session):
    neuer_nutzer(session, "stb@x.example", "steuerberater")
    nutzer = session.execute(select(Nutzer).where(Nutzer.email == "stb@x.example")).scalar_one()
    daten = {"email": "stb@x.example", "passwort": ADMIN_PASSWORT}

    aendere_nutzer(nutzer, zugang_bis=date.today(), admin_id=admin.id)
    assert client.post("/anmelden", data=daten).status_code == 302  # heute noch gültig
    client.post("/abmelden")

    aendere_nutzer(nutzer, zugang_bis=date.today() - timedelta(days=1), admin_id=admin.id)
    assert client.post("/anmelden", data=daten).status_code == 200


def test_deaktivieren_beendet_laufende_sitzung(client, admin, session):
    nutzer = neuer_nutzer(session, "m@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "m@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get("/").status_code == 200
    aendere_nutzer(nutzer, aktiv=False, admin_id=admin.id)
    assert client.get("/").status_code == 302


# ---------- Oberfläche ----------

EINSTELLUNGEN = ["/einstellungen/firma", "/einstellungen/nutzer", "/einstellungen/rechte"]


@pytest.mark.parametrize("pfad", EINSTELLUNGEN)
@pytest.mark.parametrize("rolle", ["buchhalter", "mitarbeiter", "steuerberater"])
def test_einstellungen_nur_fuer_admin(client, admin, session, rolle, pfad):
    neuer_nutzer(session, f"{rolle}@x.example", rolle)
    client.post("/anmelden", data={"email": f"{rolle}@x.example", "passwort": ADMIN_PASSWORT})
    assert client.get(pfad).status_code == 403
    assert client.post(pfad, data={}).status_code == 403


@pytest.mark.parametrize("pfad", EINSTELLUNGEN)
def test_einstellungen_fuer_admin(angemeldet, pfad):
    assert angemeldet.get(pfad).status_code == 200


def test_nutzer_anlegen_mit_vergangenem_zugangsende_abgewiesen(angemeldet, session):
    gestern = (date.today() - timedelta(days=1)).isoformat()
    antwort = angemeldet.post(
        "/einstellungen/nutzer",
        data={
            "name": "Tina Steuer",
            "email": "tina@kanzlei.example",
            "rolle": "steuerberater",
            "passwort": "passwort-fuer-tina",
            "zugang_bis": gestern,
        },
    )
    assert antwort.status_code == 200
    assert "liegt in der Vergangenheit" in antwort.get_data(as_text=True)
    assert (
        session.execute(select(Nutzer).where(Nutzer.email == "tina@kanzlei.example")).first()
        is None
    )


def test_nutzer_anlegen_unbekannte_rolle_deutsche_meldung(angemeldet):
    antwort = angemeldet.post(
        "/einstellungen/nutzer",
        data={
            "name": "X",
            "email": "x@x.example",
            "rolle": "root",
            "passwort": "langes-passwort-1",
        },
    )
    seite = antwort.get_data(as_text=True)
    assert "Bitte aus der Liste wählen." in seite
    assert "Not a valid" not in seite


def test_nutzer_bearbeiten_seite_ist_sauber(angemeldet, admin):
    seite = angemeldet.get(f"/einstellungen/nutzer/{admin.id}").get_data(as_text=True)
    titel = seite.split("<title>")[1].split("</title>")[0]
    assert "<" not in titel
    assert '<main class="inhalt schmal">' in seite


def test_nutzer_anlegen_ueber_oberflaeche(angemeldet, session):
    antwort = angemeldet.post(
        "/einstellungen/nutzer",
        data={
            "name": "Stefan Steuer",
            "email": "stefan@kanzlei.example",
            "rolle": "steuerberater",
            "passwort": "Zebra-Kaffee-Wolke-42",
            "zugang_bis": "2099-12-31",
        },
    )
    assert antwort.status_code == 302
    nutzer = session.execute(
        select(Nutzer).where(Nutzer.email == "stefan@kanzlei.example")
    ).scalar_one()
    assert nutzer.rolle == "steuerberater"
    assert nutzer.zugang_bis == date(2099, 12, 31)
    liste = angemeldet.get("/einstellungen/nutzer").get_data(as_text=True)
    assert "Stefan Steuer" in liste


def test_nutzer_doppelte_email_ueber_oberflaeche(angemeldet):
    antwort = angemeldet.post(
        "/einstellungen/nutzer",
        data={
            "name": "X",
            "email": ADMIN_EMAIL,
            "rolle": "mitarbeiter",
            "passwort": "Zebra-Kaffee-Wolke-42",
        },
    )
    assert antwort.status_code == 200
    assert "bereits vergeben" in antwort.get_data(as_text=True)


def test_letzter_admin_ueber_oberflaeche(angemeldet, admin):
    antwort = angemeldet.post(
        f"/einstellungen/nutzer/{admin.id}",
        data={"name": admin.name, "email": admin.email, "rolle": "mitarbeiter", "aktiv": "y"},
    )
    assert antwort.status_code == 200
    assert "mindestens einen aktiven Admin" in antwort.get_data(as_text=True)


def test_nutzer_bearbeiten_ueber_oberflaeche(angemeldet, session):
    nutzer = neuer_nutzer(session, "m@x.example", "mitarbeiter")
    antwort = angemeldet.post(
        f"/einstellungen/nutzer/{nutzer.id}",
        data={"name": "Mia Mitarbeit", "email": "m@x.example", "rolle": "buchhalter"},
    )
    assert antwort.status_code == 302
    session.refresh(nutzer)
    assert nutzer.name == "Mia Mitarbeit"
    assert nutzer.rolle == "buchhalter"
    assert nutzer.aktiv is False  # Haken „aktiv“ nicht gesetzt


def test_unbekannter_nutzer_404(angemeldet):
    assert angemeldet.get("/einstellungen/nutzer/99999").status_code == 404


def test_rechte_ueber_oberflaeche(angemeldet, session):
    daten = {
        f"{rolle}:{recht}": "y" for rolle, rechte in STANDARDRECHTE.items() for recht in rechte
    }
    daten["mitarbeiter:zahlungen"] = "y"
    antwort = angemeldet.post("/einstellungen/rechte", data=daten)
    assert antwort.status_code == 302
    assert Recht.ZAHLUNGEN in rechte_matrix()[Rolle.MITARBEITER]


def test_rechte_formular_ignoriert_nur_admin_rechte(angemeldet):
    daten = {"buchhalter:nutzer_verwalten": "y", "buchhalter:belege": "y"}
    angemeldet.post("/einstellungen/rechte", data=daten)
    assert rechte_matrix()[Rolle.BUCHHALTER] == {Recht.BELEGE}


def test_einstellbare_rechte_vollstaendig():
    assert set(EINSTELLBAR) | NUR_ADMIN | {Recht.ANSEHEN} == set(Recht)


@pytest.mark.parametrize(
    "passwort",
    ["Passwort2026!", "qwertzuiop12", "aaaaaaaaaaaa", "1234567890", "stefan-kanzlei-99"],
)
def test_schwache_passwoerter_beim_anlegen_abgelehnt(angemeldet, session, passwort):
    antwort = angemeldet.post(
        "/einstellungen/nutzer",
        data={
            "name": "Stefan Steuer",
            "email": "stefan@kanzlei.example",
            "rolle": "buchhalter",
            "passwort": passwort,
        },
    )
    assert antwort.status_code == 200
    assert (
        session.execute(select(Nutzer).where(Nutzer.email == "stefan@kanzlei.example")).first()
        is None
    )


def test_gutes_passwort_ohne_sonderzeichen_ist_erlaubt():
    from app.domain.passwort import schwaches_passwort

    assert schwaches_passwort("Zebra Kaffee Wolke vierzig", ("stefan@kanzlei.example",)) is None
    assert schwaches_passwort("Passwort", ()) is not None
    assert (
        schwaches_passwort("lisa-ist-toll-heute", ("lisa@weber.example", "Lisa Weber")) is not None
    )
