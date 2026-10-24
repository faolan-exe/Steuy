import io

import pytest
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select

from app.domain.drucklayout import (
    LAYOUTS,
    Layout,
    LayoutUngueltig,
    kontrastfarbe,
    mische,
    pruefe,
)
from app.models import Drucklayout
from app.services import drucklayout as dienst
from app.services.pdf import rendere_rechnung
from tests.test_rechnungen import auftritt, bank, kunde, speichern  # noqa: F401
from tests.test_zahlungen import rechnung  # noqa: F401


def bild(format="PNG", groesse=(200, 80)):
    puffer = io.BytesIO()
    Image.new("RGB", groesse, "#2e7d4f").save(puffer, format=format)
    return puffer.getvalue()


def pdf_text(inhalt: bytes) -> str:
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(inhalt)).pages)


@pytest.fixture
def mit_app(app):
    with app.app_context():
        yield


# ---------- Domain ----------


def test_pruefe_nimmt_gueltige_werte_und_haken():
    layout = pruefe({"layout": "3", "akzent": "#AABBCC", "schrift": "serif", "zeige_pos": "y"})
    assert (layout.layout, layout.akzent, layout.schrift) == (3, "#aabbcc", "serif")
    assert layout.zeige_pos is True and layout.zeige_bank is False


@pytest.mark.parametrize(
    "werte",
    [
        {"layout": "0"},
        {"layout": "6"},
        {"layout": "x"},
        {"akzent": "rot"},
        {"akzent": "#12345"},
        {"akzent": "url(javascript:1)"},
        {"schrift": "Comic Sans"},
        {"schrift_text": "30"},
        {"schrift_titel": "5"},
        {"logo_prozent": "1000"},
    ],
)
def test_pruefe_lehnt_ungueltiges_ab(werte):
    with pytest.raises(LayoutUngueltig):
        pruefe(werte)


def test_farben():
    assert kontrastfarbe("#ffffff") == "#111111" and kontrastfarbe("#1f5fa8") == "#ffffff"
    assert mische("#000000", 0.5) == "#808080" and mische("#2e7d4f", 1.0) == "#ffffff"
    assert len(LAYOUTS) == 5


# ---------- Dienst ----------


def test_speichern_und_zuruecksetzen(admin, session, mit_app):
    assert dienst.aktuell() == Layout()
    dienst.speichere(pruefe({"layout": "4", "akzent": "#b23a48", "schrift": "serif"}), admin.id)
    zeile = session.execute(select(Drucklayout)).scalar_one()
    assert (zeile.layout, zeile.akzent, zeile.schrift) == (4, "#b23a48", "serif")
    dienst.zuruecksetzen(admin.id)
    assert dienst.aktuell() == Layout()


def test_logo_ablegen_pruefen_entfernen(admin, mit_app):
    assert dienst.logo_daten_uri() is None
    dienst.setze_logo(bild("PNG"), admin.id)
    assert dienst.logo_daten_uri().startswith("data:image/png;base64,")
    dienst.setze_logo(bild("JPEG"), admin.id)
    assert dienst.logo_daten_uri().startswith("data:image/jpeg;base64,")
    dienst.entferne_logo(admin.id)
    assert dienst.logo_daten_uri() is None


@pytest.mark.parametrize(
    ("inhalt", "text"),
    [
        (b"", "leer"),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            "PNG oder JPG",
        ),
        (b"%PDF-1.4 kein Bild", "PNG oder JPG"),
        (b"\x89PNG\r\n\x1a\nkaputt", "beschädigt"),
        (b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024), "größer als 2 MB"),
    ],
)
def test_ungueltiges_logo_abgelehnt(admin, mit_app, inhalt, text):
    with pytest.raises(dienst.LogoUngueltig, match=text):
        dienst.setze_logo(inhalt, admin.id)
    assert dienst.logo_daten_uri() is None


def test_zu_grosses_logo_in_pixeln_abgelehnt(admin, mit_app):
    with pytest.raises(dienst.LogoUngueltig, match="zu groß"):
        dienst.setze_logo(bild("PNG", (7000, 10)), admin.id)


# ---------- Oberfläche ----------


def test_seite_zeigt_editor(angemeldet):
    seite = angemeldet.get("/einstellungen/drucklayout").get_data(as_text=True)
    assert "Vorschau" in seite and "Klassisch" in seite and "Seitenleiste" in seite
    assert 'name="logo_prozent"' in seite and 'name="akzent"' in seite
    assert ">Drucklayout</a>" in angemeldet.get("/einstellungen/firma").get_data(as_text=True)


def test_speichern_ueber_oberflaeche(angemeldet, session):
    antwort = angemeldet.post(
        "/einstellungen/drucklayout",
        data={
            "layout": "5",
            "akzent": "#1f5fa8",
            "schrift": "dejavu",
            "schrift_text": "11",
            "schrift_titel": "18",
            "logo_prozent": "150",
            "zeige_pos": "y",
            "gesamt_grau": "y",
        },
    )
    assert antwort.status_code == 302
    zeile = session.execute(select(Drucklayout)).scalar_one()
    assert (zeile.layout, zeile.akzent, zeile.logo_prozent) == (5, "#1f5fa8", 150)
    assert zeile.gesamt_grau is True and zeile.zeige_fusszeile is False


def test_ungueltige_eingabe_speichert_nichts(angemeldet, session):
    antwort = angemeldet.post("/einstellungen/drucklayout", data={"layout": "9", "akzent": "#fff"})
    assert antwort.status_code == 200
    assert session.get(Drucklayout, 1) is None or session.get(Drucklayout, 1).layout == 1


def test_logo_hochladen_und_entfernen_ueber_oberflaeche(angemeldet, session):
    antwort = angemeldet.post(
        "/einstellungen/drucklayout/logo",
        data={"logo": (io.BytesIO(bild()), "logo.png")},
        content_type="multipart/form-data",
    )
    assert antwort.status_code == 302
    seite = angemeldet.get("/einstellungen/drucklayout").get_data(as_text=True)
    assert "Logo entfernen" in seite and "data:image/png;base64," in seite
    schlecht = angemeldet.post(
        "/einstellungen/drucklayout/logo",
        data={"logo": (io.BytesIO(b"<svg/>"), "logo.svg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "PNG oder JPG" in schlecht.get_data(as_text=True)
    angemeldet.post("/einstellungen/drucklayout/logo/entfernen")
    assert "Logo entfernen" not in angemeldet.get("/einstellungen/drucklayout").get_data(
        as_text=True
    )


def test_vorschau_mit_und_ohne_angaben(angemeldet, session):
    ohne = angemeldet.get("/einstellungen/drucklayout/vorschau").get_data(as_text=True)
    assert 'class="blatt"' in ohne and "Rechnung RE0123" in ohne and "Seitenleiste" not in ohne
    mit = angemeldet.get("/einstellungen/drucklayout/vorschau?layout=4&akzent=%23b23a48")
    assert "#b23a48" in mit.get_data(as_text=True) and 'class="band"' in mit.get_data(as_text=True)
    kaputt = angemeldet.get("/einstellungen/drucklayout/vorschau?layout=99")
    assert kaputt.status_code == 200


def test_zuruecksetzen_ueber_oberflaeche(angemeldet, session):
    angemeldet.post("/einstellungen/drucklayout", data={"layout": "3", "akzent": "#333333"})
    angemeldet.post("/einstellungen/drucklayout/zuruecksetzen")
    assert session.get(Drucklayout, 1).layout == 1


def test_drucklayout_nur_mit_einstellungsrecht(client, admin, session):
    from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

    neuer_nutzer(session, "mitarbeiter@x.example", "mitarbeiter")
    client.post("/anmelden", data={"email": "mitarbeiter@x.example", "passwort": ADMIN_PASSWORT})
    for methode, pfad in (
        ("get", "/einstellungen/drucklayout"),
        ("get", "/einstellungen/drucklayout/vorschau"),
        ("post", "/einstellungen/drucklayout"),
        ("post", "/einstellungen/drucklayout/logo"),
        ("post", "/einstellungen/drucklayout/logo/entfernen"),
        ("post", "/einstellungen/drucklayout/zuruecksetzen"),
    ):
        assert getattr(client, methode)(pfad).status_code == 403, pfad


# ---------- Wirkung auf die PDFs ----------


@pytest.mark.parametrize("nr", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("mit_logo", [False, True])
def test_pdf_in_jedem_layout_mit_und_ohne_logo(rechnung, admin, mit_app, nr, mit_logo):  # noqa: F811
    dienst.speichere(pruefe({"layout": nr, "akzent": "#1f5fa8", "zeige_fusszeile": "y"}), admin.id)
    if mit_logo:
        dienst.setze_logo(bild(), admin.id)
    else:
        dienst.entferne_logo(admin.id)
    inhalt = rendere_rechnung(rechnung, entwurf=True)
    text = pdf_text(inhalt)
    assert inhalt.startswith(b"%PDF") and f"Rechnung {rechnung.nummer}" in text
    assert "Auftritt" in text and "152,20" in text
    # ohne Logo steht der Firmenname im Kopf, mit Logo nicht zusätzlich als große Wortmarke
    assert ("Musterwerkstatt" in text) is True


def test_pos_spalte_und_fusszeile_abschaltbar(rechnung, admin, mit_app):  # noqa: F811
    dienst.speichere(pruefe({"layout": "1", "zeige_pos": "y", "zeige_fusszeile": "y"}), admin.id)
    an = pdf_text(rendere_rechnung(rechnung, entwurf=False))
    assert "Pos." in an and "Steuernummer" not in an  # Steuer-Haken fehlte
    dienst.speichere(pruefe({"layout": "1"}), admin.id)
    aus = pdf_text(rendere_rechnung(rechnung, entwurf=False))
    assert "Pos." not in aus and "Seite 1 von 1" in aus


def test_lieferschein_und_mahnung_nutzen_das_layout(angemeldet, rechnung, admin, session, mit_app):  # noqa: F811
    from app.models import Rechnung
    from app.services.rechnungen import lieferschein_aus_rechnung

    dienst.speichere(pruefe({"layout": "3", "akzent": "#b23a48", "zeige_fusszeile": "y"}), admin.id)
    lieferschein = lieferschein_aus_rechnung(rechnung, admin.id)
    assert "Lieferschein LS0001" in pdf_text(rendere_rechnung(lieferschein, entwurf=False))
    angemeldet.post(f"/rechnungen/{rechnung.id}/mahnungen")
    mahnung = session.get(Rechnung, rechnung.id).mahnungen[0]
    mahn = angemeldet.get(f"/rechnungen/{rechnung.id}/mahnungen/{mahnung.id}/pdf")
    assert mahn.status_code == 200 and mahn.data.startswith(b"%PDF")


def test_logo_ersetzt_den_firmennamen_nicht(rechnung, admin, mit_app):  # noqa: F811
    dienst.setze_logo(bild(), admin.id)
    mit = pdf_text(rendere_rechnung(rechnung, entwurf=True))
    assert mit.count("Musterwerkstatt") >= 2  # Kopf und Fußzeile
    dienst.speichere(
        pruefe({"layout": "2", "zeige_fusszeile": "y", "zeige_absenderzeile": "y"}), admin.id
    )
    ohne_namen = pdf_text(rendere_rechnung(rechnung, entwurf=True))
    assert ohne_namen.count("Musterwerkstatt") == mit.count("Musterwerkstatt") - 1
    dienst.entferne_logo(admin.id)
    assert pdf_text(rendere_rechnung(rechnung, entwurf=True)).count("Musterwerkstatt") >= 2


def test_logo_platz_standard_und_auswahl():
    from app.domain.drucklayout import LOGO_STANDARD

    assert {nr: pruefe({"layout": nr}).logo_platz for nr in range(1, 6)} == LOGO_STANDARD
    assert pruefe({"layout": "1", "logo_position": "mitte"}).logo_platz == "mitte"
    with pytest.raises(LayoutUngueltig):
        pruefe({"logo_position": "oben"})


def test_logo_platz_wirkt_in_der_vorschau(angemeldet):
    def vorschau(platz):
        antwort = angemeldet.get(
            f"/einstellungen/drucklayout/vorschau?layout=2&logo_position={platz}"
        )
        return antwort.get_data(as_text=True)

    assert "row-reverse" in vorschau("rechts") and "row-reverse" not in vorschau("links")
    assert "justify-content: center" in vorschau("mitte")
    seite = angemeldet.get("/einstellungen/drucklayout").get_data(as_text=True)
    assert 'name="logo_position"' in seite and ">Mitte<" in seite


def test_logo_platz_wird_gespeichert(angemeldet, session):
    angemeldet.post("/einstellungen/drucklayout", data={"layout": "2", "logo_position": "rechts"})
    assert session.get(Drucklayout, 1).logo_position == "rechts"
