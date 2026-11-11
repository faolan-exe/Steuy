# ruff: noqa: F811
"""Kundenportal: persönliche Links zu Belegen, PLZ-Abfrage, Angebot online annehmen."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Gewerbe, Kontakt, Kundenlink, Protokoll
from app.services import kundenportal
from app.services.mail import ausgang
from app.services.rechnungen import finalisiere, neuer_entwurf
from tests.test_angebote import angebot  # noqa: F401
from tests.test_email import mail_eingerichtet  # noqa: F401
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401

ADRESSE = "https://rechnung.musterwerkstatt.example"


@pytest.fixture
def portal(session, admin):
    gewerbe = session.get(Gewerbe, 1)
    gewerbe.oeffentliche_adresse = ADRESSE
    session.commit()
    return gewerbe


@pytest.fixture
def rechnung(angemeldet, admin, kunde, bank, app, portal):
    entwurf = neuer_entwurf(admin.id)
    speichern(angemeldet, entwurf, kunde, rechnungsdatum=date.today().isoformat())
    with app.app_context():
        return finalisiere(entwurf, admin.id)


def schluessel(app, beleg) -> str:
    with app.app_context():
        return kundenportal.url_fuer(beleg).rsplit("/", 1)[1]


@pytest.fixture
def gast(app, session):
    """Ein Kunde ohne Anmeldung, in einem eigenen Browser."""
    return app.test_client()


def freischalten(gast, s, plz="50667"):
    return gast.post(f"/k/{s}", data={"plz": plz})


# ---------- Link erzeugen ----------


def test_link_nur_mit_portal_und_adresse(app, rechnung, session, portal):
    with app.app_context():
        assert kundenportal.url_fuer(rechnung).startswith(f"{ADRESSE}/k/")
        # Gleicher Beleg, gleicher Link
        assert kundenportal.url_fuer(rechnung) == kundenportal.url_fuer(rechnung)
        portal.kundenportal = False
        session.commit()
        assert kundenportal.url_fuer(rechnung) is None
        portal.kundenportal = True
        portal.oeffentliche_adresse = None
        session.commit()
        app.config["BASIS_URL"] = ""
        assert kundenportal.url_fuer(rechnung) is None


def test_kein_link_fuer_entwuerfe(app, angemeldet, admin, kunde, bank, portal):
    entwurf = neuer_entwurf(admin.id)
    with app.app_context(), pytest.raises(kundenportal.PortalFehler):
        kundenportal.erzeuge_link(entwurf)


def test_schluessel_nur_als_hash_und_verschluesselt(app, rechnung, session):
    s = schluessel(app, rechnung)
    link = session.execute(select(Kundenlink)).scalar_one()
    assert s not in (link.schluessel_hash, link.schluessel_geheim)
    assert len(s) >= 32


def test_link_steht_in_der_mail_mit_knopf(app, angemeldet, rechnung, mail_eingerichtet):
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}/senden").get_data(as_text=True)
    assert f"{ADRESSE}/k/" in seite
    with app.app_context():
        url = kundenportal.url_fuer(rechnung)
        text = f"Guten Tag,\n\nOnline ansehen:\n{url}\n\nGrüße"
        angemeldet.post(
            f"/rechnungen/{rechnung.id}/senden",
            data={"an": "kunde@example.de", "betreff": "Rechnung", "text": text},
        )
        nachricht = ausgang()[-1]
    html = nachricht.get_body(("html",)).get_content()
    assert f'href="{url}"' in html and "Rechnung ansehen" in html
    assert url in nachricht.get_body(("plain",)).get_content()


def test_html_mail_maskiert_eingaben():
    from app.domain.mail import als_html

    html = als_html("Hallo <script>alert(1)</script>\n\nhttps://x.example/k/abc", None)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '<a href="https://x.example/k/abc"' in html


# ---------- Zugriff des Kunden ----------


def test_unbekannter_link_404_ohne_details(gast, rechnung):
    antwort = gast.get("/k/gibt-es-nicht")
    assert antwort.status_code == 404
    assert "nicht (mehr) gültig" in antwort.get_data(as_text=True)


def test_plz_schuetzt_beleg_und_dateien(app, gast, rechnung):
    s = schluessel(app, rechnung)
    seite = gast.get(f"/k/{s}").get_data(as_text=True)
    assert "Postleitzahl" in seite and rechnung.nummer not in seite
    assert gast.get(f"/k/{s}/pdf").status_code == 302
    assert freischalten(gast, s, "99999").status_code == 401
    assert freischalten(gast, s, " 50667 ").status_code == 302
    seite = gast.get(f"/k/{s}").get_data(as_text=True)
    assert rechnung.nummer in seite and "Bezahlen" in seite and "DE" in seite
    pdf = gast.get(f"/k/{s}/pdf?herunterladen=1")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    assert pdf.headers["Content-Disposition"].startswith("attachment")


def test_plz_sperre_nach_fuenf_fehlversuchen(app, gast, rechnung):
    s = schluessel(app, rechnung)
    for _ in range(5):
        assert freischalten(gast, s, "00000").status_code == 401
    antwort = freischalten(gast, s)  # jetzt auch mit richtiger PLZ gesperrt
    assert antwort.status_code == 401 and "Zu viele Versuche" in antwort.get_data(as_text=True)


def test_ohne_plz_abfrage_direkt_sichtbar(app, gast, rechnung, portal, session):
    portal.kundenportal_plz = False
    session.commit()
    assert rechnung.nummer in gast.get(f"/k/{schluessel(app, rechnung)}").get_data(as_text=True)


def test_abruf_wird_gezaehlt(app, gast, rechnung, session):
    s = schluessel(app, rechnung)
    freischalten(gast, s)
    gast.get(f"/k/{s}")
    link = session.execute(select(Kundenlink)).scalar_one()
    assert link.abrufe == 1 and link.zuletzt_abgerufen


def test_kopfzeilen_ohne_referrer_und_ohne_index(app, gast, rechnung):
    antwort = gast.get(f"/k/{schluessel(app, rechnung)}")
    assert antwort.headers["Referrer-Policy"] == "no-referrer"
    assert "noindex" in antwort.headers["X-Robots-Tag"]
    assert antwort.headers["Cache-Control"] == "no-store"


def test_gesperrter_link_funktioniert_nicht_mehr(app, angemeldet, gast, rechnung, session):
    alt = schluessel(app, rechnung)
    antwort = angemeldet.post(f"/rechnungen/{rechnung.id}/kundenlink")
    assert antwort.status_code == 302
    assert gast.get(f"/k/{alt}").status_code == 404
    neu = schluessel(app, rechnung)
    assert neu != alt and gast.get(f"/k/{neu}").status_code == 200


def test_link_erneuern_braucht_recht(app, rechnung, session):
    from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

    neuer_nutzer(session, "lesen@example.de", "steuerberater")
    client = app.test_client()
    client.post("/anmelden", data={"email": "lesen@example.de", "passwort": ADMIN_PASSWORT})
    assert client.post(f"/rechnungen/{rechnung.id}/kundenlink").status_code == 403


def test_belegseite_zeigt_link_und_abrufe(app, angemeldet, gast, rechnung):
    s = schluessel(app, rechnung)
    freischalten(gast, s)
    gast.get(f"/k/{s}")
    seite = angemeldet.get(f"/rechnungen/{rechnung.id}").get_data(as_text=True)
    assert f"{ADRESSE}/k/{s}" in seite and "Vom Kunden angesehen: 1×" in seite


def test_status_ueberfaellig_und_bezahlt(app, rechnung):
    with app.app_context():
        spaeter = (rechnung.faellig_am or date.today()) + timedelta(days=1)
        assert kundenportal.status(rechnung, spaeter).text == "Überfällig"
        rechnung.status = "bezahlt"
        assert kundenportal.status(rechnung, spaeter).text == "Bezahlt"


# ---------- Angebot online annehmen ----------


@pytest.fixture
def angebot_link(app, angebot, portal, session):
    portal.kundenportal_plz = False
    session.commit()
    return schluessel(app, angebot)


def test_angebot_annehmen(app, gast, angebot, angebot_link, session):
    seite = gast.get(f"/k/{angebot_link}").get_data(as_text=True)
    assert "Angebot annehmen" in seite
    antwort = gast.post(
        f"/k/{angebot_link}/entscheiden",
        data={
            "entscheidung": "annehmen",
            "name": "Max Beispiel",
            "verbindlich": "ja",
            "kommentar": "Gern im Januar",
        },
    )
    assert antwort.status_code == 302
    session.refresh(angebot)
    assert angebot.status == "angenommen"
    link = session.execute(select(Kundenlink)).scalar_one()
    assert link.entschieden_von == "Max Beispiel" and link.kommentar == "Gern im Januar"
    eintrag = session.execute(
        select(Protokoll).where(Protokoll.aktion == "angebot_angenommen_online")
    ).scalar_one()
    assert eintrag.details["name"] == "Max Beispiel"
    # Ein zweites Mal geht nicht
    gast.post(f"/k/{angebot_link}/entscheiden", data={"entscheidung": "ablehnen"})
    session.refresh(angebot)
    assert angebot.status == "angenommen"


def test_annehmen_braucht_bestaetigung_und_namen(app, gast, angebot, angebot_link, session):
    gast.post(f"/k/{angebot_link}/entscheiden", data={"entscheidung": "annehmen", "name": "X"})
    gast.post(
        f"/k/{angebot_link}/entscheiden", data={"entscheidung": "annehmen", "verbindlich": "ja"}
    )
    session.refresh(angebot)
    assert angebot.status == "offen"


def test_angebot_ablehnen(app, gast, angebot, angebot_link, session):
    gast.post(f"/k/{angebot_link}/entscheiden", data={"entscheidung": "ablehnen"})
    session.refresh(angebot)
    assert angebot.status == "abgelehnt"


def test_abgelaufenes_angebot_nicht_annehmbar(app, gast, angebot, angebot_link, session):
    angebot.gueltig_bis = date.today() - timedelta(days=1)
    with pytest.raises(Exception):  # noqa: B017  Trigger: festgeschriebene Belege unveränderlich
        session.commit()
    session.rollback()
    with app.app_context():
        assert not kundenportal.kann_entscheiden(angebot, date.today() + timedelta(days=60))


def test_benachrichtigung_an_eigenes_postfach(app, gast, angebot, angebot_link, mail_eingerichtet):
    with app.app_context():
        ausgang().clear()
    gast.post(
        f"/k/{angebot_link}/entscheiden",
        data={"entscheidung": "annehmen", "name": "Max", "verbindlich": "ja"},
    )
    with app.app_context():
        nachricht = ausgang()[-1]
    assert nachricht["To"] == mail_eingerichtet.email and "angenommen" in nachricht["Subject"]


def test_link_zu_anderem_kontakt_bleibt_beim_beleg(app, gast, rechnung, session):
    """Wer den Link kennt, sieht genau diesen einen Beleg, sonst nichts."""
    s = schluessel(app, rechnung)
    freischalten(gast, s)
    assert gast.get("/rechnungen").status_code == 302  # interne Seiten weiter nur mit Anmeldung
    assert gast.get(f"/rechnungen/{rechnung.id}/pdf").status_code in (302, 403)
    assert session.execute(select(Kontakt)).scalars().first()


def test_finalisieren_und_senden_in_einem_schritt(
    app, angemeldet, admin, kunde, bank, portal, mail_eingerichtet, session
):
    kunde.email = "kunde@example.de"
    session.commit()
    entwurf = neuer_entwurf(admin.id)
    speichern(angemeldet, entwurf, kunde, rechnungsdatum=date.today().isoformat())
    seite = angemeldet.get(f"/rechnungen/{entwurf.id}/vorschau").get_data(as_text=True)
    assert "Finalisieren und senden" in seite
    antwort = angemeldet.post(f"/rechnungen/{entwurf.id}/finalisieren", data={"danach": "senden"})
    assert antwort.headers["Location"].endswith(f"/rechnungen/{entwurf.id}/senden")
    seite = angemeldet.get(antwort.headers["Location"]).get_data(as_text=True)
    assert "kunde@example.de" in seite and f"{ADRESSE}/k/" in seite
