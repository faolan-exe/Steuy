"""Besucht jede Seite der App mit der Musterfirma und prüft sie auf still falsche Ausgaben.

Siehe tests/seitenpruefung.py: maskierte Attribute, nicht definierte Variablen, None in der
Ausgabe, fehlende Formularfelder, von der CSP blockierte Skripte, Labels ohne Feld, doppelte
IDs, tote interne Links und Serverfehler. Neue Seiten werden automatisch mitgeprüft.
"""

import re
from urllib.parse import urlsplit

import pytest
from flask import template_rendered
from flask_wtf import FlaskForm
from sqlalchemy import select

from app.models import (
    Artikel,
    Beleg,
    Buchung,
    Kontakt,
    Mahnung,
    Nutzer,
    Rechnung,
    WiederkehrendeRechnung,
    Zahlung,
)
from tests.seitenpruefung import (
    MeldendesUndefined,
    formulare_von,
    ids_von,
    links_von,
    pruefe_html,
)

# Seiten, die nicht HTML liefern oder nur weiterleiten: nur Status prüfen
OHNE_HTML = re.compile(r"(\.csv|\.pdf|\.zip|/pdf|/xml|/datei|/nachweis|/status)$")
# Seiten mit Seiteneffekt oder ohne Sinn in diesem Rundgang
AUSGELASSEN = {"auth.anmelden", "auth.zweiter_faktor", "einrichtung.einrichten", "static"}
# Formulare mit diesen Zielen schickt der Rundgang nie ab (Seiteneffekte nach außen)
GEFAEHRLICH = ("loeschen", "abmelden", "senden", "update/starten", "stornieren", "test")


def _ids(session, modell, wo=None, anzahl=8):
    abfrage = select(modell.id).order_by(modell.id)
    if wo is not None:
        abfrage = abfrage.where(wo)
    return list(session.execute(abfrage.limit(anzahl)).scalars())


@pytest.fixture
def musterfirma(app, session, client):
    from app.services import kundenportal

    musterfirma_bauen = None
    if musterfirma_bauen is None:
        pytest.skip("Die Musterfirma für den Rundgang gibt es nur im Entwicklungsrepository")
    with app.app_context():
        musterfirma_bauen()
        gewerbe = kundenportal.aktuelles_gewerbe()
        gewerbe.oeffentliche_adresse = "https://rechnung.example"
        gewerbe.e_rechnung = True
        session.commit()
        schluessel = []
        for belegart in ("rechnung", "angebot", "lieferschein", "korrektur"):
            r = (
                session.execute(
                    select(Rechnung).where(
                        Rechnung.belegart == belegart, Rechnung.nummer.is_not(None)
                    )
                )
                .scalars()
                .first()
            )
            schluessel.append(kundenportal.url_fuer(r).rsplit("/", 1)[1])
        nutzer = session.execute(select(Nutzer)).scalars().first()
        nutzer.rundgang_schritt = None
        session.commit()
        from app.models import Kundenlink

        link_ids = list(session.execute(select(Kundenlink.id)).scalars())
    with client.session_transaction() as sitzung:
        sitzung["_user_id"] = str(nutzer.id)
        sitzung["_fresh"] = True
        sitzung["kundenlinks"] = link_ids  # PLZ gilt als bestätigt: ganze Portalseite prüfen
    return schluessel


def _werte(session, schluessel) -> dict[str, list]:
    rechnungen = []
    for belegart in ("rechnung", "angebot", "lieferschein", "korrektur"):
        rechnungen += _ids(session, Rechnung, Rechnung.belegart == belegart, 3)
    rechnungen += _ids(session, Rechnung, Rechnung.status == "entwurf", 3)
    return {
        "rechnung_id": rechnungen,
        "artikel_id": _ids(session, Artikel),
        "beleg_id": _ids(session, Beleg),
        "buchung_id": _ids(session, Buchung),
        "kontakt_id": _ids(session, Kontakt),
        "nutzer_id": _ids(session, Nutzer),
        "vorlage_id": _ids(session, WiederkehrendeRechnung),
        "schluessel": schluessel,
    }


def _adressen(app, session, schluessel) -> list[str]:
    werte = _werte(session, schluessel)
    mahnungen = list(session.execute(select(Mahnung)).scalars())
    zahlungen = list(
        session.execute(select(Zahlung).where(Zahlung.rechnung_id.is_not(None))).scalars()
    )
    adressen = []
    for regel in app.url_map.iter_rules():
        if "GET" not in regel.methods or regel.endpoint in AUSGELASSEN:
            continue
        argumente = set(regel.arguments)
        if not argumente:
            adressen.append(regel.rule)
        elif argumente == {"rechnung_id", "mahnung_id"}:
            adressen += [
                regel.rule.replace("<int:rechnung_id>", str(m.rechnung_id)).replace(
                    "<int:mahnung_id>", str(m.id)
                )
                for m in mahnungen[:4]
            ]
        elif argumente == {"rechnung_id", "zahlung_id"}:
            adressen += [
                regel.rule.replace("<int:rechnung_id>", str(z.rechnung_id)).replace(
                    "<int:zahlung_id>", str(z.id)
                )
                for z in zahlungen[:3]
            ]
        elif argumente == {"schluessel", "mahnung_id"}:
            continue  # Mahnungen im Portal prüft test_kundenportal
        elif len(argumente) == 1:
            (name,) = argumente
            for wert in werte.get(name, []):
                adressen.append(re.sub(r"<(?:\w+:)?" + name + ">", str(wert), regel.rule))
        else:
            raise AssertionError(f"Unbekannte Parameter in {regel.rule}: {argumente}")
    return adressen


def test_alle_seiten_ohne_still_falsche_ausgaben(app, session, client, musterfirma):
    alt = app.jinja_env.undefined
    app.jinja_env.undefined = MeldendesUndefined
    # Wie im Betrieb mit CSRF-Schutz, sonst fehlt das Feld csrf_token in den Formularen
    app.config["WTF_CSRF_ENABLED"] = True
    formulare: list = []

    def merke(sender, template, context, **extra):
        formulare.extend(v for v in context.values() if isinstance(v, FlaskForm))

    template_rendered.connect(merke, app)
    funde: dict[str, list[str]] = {}
    besucht: set[str] = set()
    try:
        # (Adresse, Herkunft): Herkunft None = selbst gebaut, sonst die Seite mit dem Link
        offen = [(a, None) for a in _adressen(app, session, musterfirma)]
        seiten_ids: dict[str, set[str]] = {}
        anker: list[tuple[str, str, str]] = []
        abgeschickt: set[tuple[str, str]] = set()
        while offen:
            adresse, herkunft = offen.pop(0)
            if adresse in besucht or len(besucht) > 4000:
                continue
            besucht.add(adresse)
            formulare.clear()
            try:
                antwort = client.get(adresse)
            except Exception as fehler:  # noqa: BLE001  jeder Absturz ist ein Fund
                funde.setdefault(adresse, []).append(f"Absturz: {type(fehler).__name__}: {fehler}")
                continue
            if antwort.status_code >= 500:
                funde.setdefault(adresse, []).append(f"Status {antwort.status_code}")
                continue
            if antwort.status_code == 404 and herkunft:
                funde.setdefault(herkunft, []).append(f"Toter Link: {adresse}")
            if antwort.mimetype != "text/html" or antwort.status_code != 200:
                continue
            html = antwort.get_data(as_text=True)
            for fund in pruefe_html(html, formulare):
                funde.setdefault(adresse, []).append(fund)
            seiten_ids[adresse] = ids_von(html)
            for link in links_von(html):
                teile = urlsplit(link)
                if teile.scheme or teile.netloc:
                    continue
                pfad = teile.path or adresse.split("?")[0]
                ziel = pfad + (f"?{teile.query}" if teile.query else "")
                if teile.fragment and not teile.fragment.startswith("!"):
                    anker.append((adresse, ziel, teile.fragment))
                if not pfad.startswith("/") or pfad.startswith(("/static/", "/k/")):
                    continue
                if ziel not in besucht:
                    offen.append((ziel, adresse))
            # Formulare mit Eingabefeldern leer absenden: Fehlerseiten sind oft ungeprüft
            for methode, ziel, eingaben in formulare_von(html):
                ziel = ziel or adresse
                if methode != "post" or not eingaben or (adresse, ziel) in abgeschickt:
                    continue
                if not ziel.startswith("/") or any(w in ziel for w in GEFAEHRLICH):
                    continue
                abgeschickt.add((adresse, ziel))
                if len(abgeschickt) > 400:
                    continue
                token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
                formulare.clear()
                try:
                    antwort = client.post(
                        ziel, data={"csrf_token": token.group(1) if token else ""}
                    )
                except Exception as fehler:  # noqa: BLE001
                    funde.setdefault(f"POST {ziel}", []).append(
                        f"Absturz: {type(fehler).__name__}: {fehler}"
                    )
                    continue
                if antwort.status_code >= 500:
                    funde.setdefault(f"POST {ziel}", []).append(f"Status {antwort.status_code}")
                elif antwort.mimetype == "text/html" and antwort.status_code in (200, 400, 422):
                    for fund in pruefe_html(antwort.get_data(as_text=True), formulare):
                        funde.setdefault(f"POST {ziel} (leer)", []).append(fund)
        for quelle, ziel, fragment in anker:
            if ziel in seiten_ids and fragment not in seiten_ids[ziel]:
                funde.setdefault(quelle, []).append(f"Anker zeigt ins Leere: {ziel}#{fragment}")
    finally:
        app.jinja_env.undefined = alt
        app.config["WTF_CSRF_ENABLED"] = False
        template_rendered.disconnect(merke, app)
    bericht = "\n".join(f"{a}\n  - " + "\n  - ".join(sorted(set(f))) for a, f in funde.items())
    # Untergrenzen: Schrumpft der Rundgang still, prüft er nichts mehr
    assert len(besucht) > 600, f"Rundgang hat nur {len(besucht)} Seiten erreicht"
    assert len(abgeschickt) > 60, f"Nur {len(abgeschickt)} Formulare abgeschickt"
    assert len(anker) > 200, f"Nur {len(anker)} Anker geprüft"
    assert not funde, f"{len(funde)} Seiten mit Funden:\n{bericht}"


# ---------- Die Prüfung selbst: findet sie, was sie finden soll? ----------


@pytest.mark.parametrize(
    "html, stichwort",
    [
        ('<input name="a" autocomplete=&#34;off&#34;>', "Maskiertes Attribut"),
        ("<p>&lt;div class=x&gt;</p>", "HTML als Text"),
        ('<input name="a" value="None">', "None ausgegeben"),
        ("<p>{{ vergessen }}</p>", "Jinja-Rest"),
        ('<button onclick="x()">', "Inline-Handler"),
        ("<script>alert(1)</script>", "ohne Nonce"),
        ('<a href="javascript:x()">', "javascript:"),
        ('<p id="a"></p><p id="a"></p>', "ID doppelt"),
        ('<label for="gibtsnicht">X</label>', "Label ohne Feld"),
    ],
)
def test_pruefung_erkennt_fehlerklassen(html, stichwort):
    assert any(stichwort in f for f in pruefe_html(html)), stichwort


def test_pruefung_laesst_korrektes_html_in_ruhe():
    html = (
        '<label for="a">A</label><input id="a" name="a" autocomplete="off" value="1">'
        '<script nonce="x">1</script><script src="/x.js"></script>'
        '<template><p id="t"></p><p id="t"></p></template>'
    )
    assert pruefe_html(html) == []


def test_pruefung_meldet_teilweise_fehlende_formularfelder(app):
    from wtforms import StringField

    class F(FlaskForm):
        da = StringField()
        fehlt = StringField()

    with app.test_request_context():
        befund = pruefe_html('<input name="da">', [F(meta={"csrf": False})])
    assert any("F.fehlt" in f for f in befund)


def test_nicht_definierte_variable_faellt_auf(app):
    from jinja2 import Environment
    from jinja2.exceptions import UndefinedError

    umgebung = Environment(undefined=MeldendesUndefined, autoescape=True)
    assert umgebung.from_string("{% if x %}ja{% endif %}").render() == ""
    with pytest.raises(UndefinedError):
        umgebung.from_string("{{ x }}").render()
