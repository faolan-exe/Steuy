"""Hell, dunkel oder wie das System: Einstellung je Nutzer und Sonne/Mond-Knopf in der Leiste."""

import re
from pathlib import Path

from tests.conftest import ADMIN_PASSWORT, neuer_nutzer

CSS = (Path(__file__).parent.parent / "app/web/static/css/app.css").read_text()
FETCH = {"X-Requested-With": "fetch"}


def _attribut(seite: str) -> str | None:
    kopf = re.search(r"<html[^>]*>", seite).group(0)
    treffer = re.search(r'data-farbschema="(\w+)"', kopf)
    return treffer.group(1) if treffer else None


def test_standard_folgt_dem_system(angemeldet, admin):
    assert admin.farbschema == "auto"
    seite = angemeldet.get("/").get_data(as_text=True)
    assert _attribut(seite) is None  # ohne Attribut entscheidet prefers-color-scheme
    assert 'aria-label="Hell oder dunkel umschalten"' in seite
    assert '<meta name="color-scheme" content="light dark">' in seite


def test_dunkel_wird_gespeichert_und_auf_jeder_seite_gesetzt(angemeldet, admin):
    antwort = angemeldet.post(
        "/einstellungen/darstellung", data={"farbschema": "dunkel"}, headers=FETCH
    )
    assert antwort.status_code == 200 and antwort.get_json()["ok"]
    assert admin.farbschema == "dunkel"
    for pfad in ("/", "/rechnungen", "/einstellungen/darstellung", "/profil"):
        assert _attribut(angemeldet.get(pfad).get_data(as_text=True)) == "dunkel", pfad
    seite = angemeldet.get("/einstellungen/darstellung").get_data(as_text=True)
    assert re.search(r'value="dunkel" checked', seite)
    # Der Knopf schlägt ohne JavaScript das Gegenteil vor
    assert re.search(r'name="farbschema" value="hell"', seite)

    angemeldet.post("/einstellungen/darstellung", data={"farbschema": "auto"}, headers=FETCH)
    assert admin.farbschema == "auto"
    assert _attribut(angemeldet.get("/").get_data(as_text=True)) is None


def test_ungueltiger_wert_wird_abgelehnt(angemeldet, admin):
    antwort = angemeldet.post("/einstellungen/darstellung", data={"farbschema": "lila"})
    assert antwort.status_code == 400
    assert admin.farbschema == "auto"


def test_ohne_javascript_zurueck_zur_seite_aber_nie_nach_aussen(angemeldet):
    antwort = angemeldet.post(
        "/einstellungen/darstellung", data={"farbschema": "hell", "zurueck": "/rechnungen?"}
    )
    assert antwort.status_code == 302 and antwort.headers["Location"] == "/rechnungen"
    for fremd in ("//boese.example/", "https://boese.example/", "/\\boese.example", ""):
        antwort = angemeldet.post(
            "/einstellungen/darstellung", data={"farbschema": "hell", "zurueck": fremd}
        )
        assert antwort.headers["Location"] == "/einstellungen/darstellung", fremd


def test_jeder_nutzer_hat_sein_eigenes_schema(app, session, angemeldet, admin):
    leser = neuer_nutzer(session, "steuer@example.com", "steuerberater")
    zweiter = app.test_client()
    zweiter.post("/anmelden", data={"email": "steuer@example.com", "passwort": ADMIN_PASSWORT})
    seite = zweiter.get("/einstellungen/darstellung")
    assert seite.status_code == 200  # auch ohne Recht auf die übrigen Einstellungen
    zweiter.post("/einstellungen/darstellung", data={"farbschema": "dunkel"}, headers=FETCH)
    assert leser.farbschema == "dunkel" and admin.farbschema == "auto"
    assert _attribut(angemeldet.get("/").get_data(as_text=True)) is None


def test_abgemeldet_kein_knopf_und_keine_aenderung(client, admin):
    assert "Hell oder dunkel umschalten" not in client.get("/anmelden").get_data(as_text=True)
    antwort = client.post("/einstellungen/darstellung", data={"farbschema": "dunkel"})
    assert antwort.status_code in (302, 401, 403)
    assert admin.farbschema == "auto"


def _variablen(block: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", block))


def test_dunkle_werte_sind_vollstaendig_und_doppelt_gleich():
    """Die dunklen Werte stehen für „auto“ (Media-Query) und für „dunkel“ (Attribut) da.
    Beide müssen gleich sein, sonst sieht dunkel je nach Weg anders aus."""
    hell = _variablen(re.search(r":root \{(.*?)\n\}", CSS, re.S).group(1))
    auto = _variablen(
        re.search(r':root:not\(\[data-farbschema="hell"\]\) \{(.*?)\n  \}', CSS, re.S).group(1)
    )
    fest = _variablen(
        re.search(r':root\[data-farbschema="dunkel"\] \{(.*?)\n\}', CSS, re.S).group(1)
    )
    assert auto == fest
    fehlend = {n for n, w in hell.items() if w.startswith("#")} - set(fest)
    assert not fehlend, f"Im Dunkelmodus fehlen {sorted(fehlend)}"


def test_keine_festen_farben_ausserhalb_der_variablen():
    """Eine feste Farbe in einer Regel bleibt im Dunkelmodus hell und fällt nur zufällig auf.
    Erlaubt: Weiß als Schrift auf farbigem Grund, die Demo-Leiste und die Schema-Vorschau,
    die ja gerade feste Farben zeigen soll."""
    ohne_variablen = re.sub(r":root[^{]*\{.*?\n\s*\}", "", CSS, flags=re.S)
    # Die Marken zusammengesetzt, sonst hält der öffentliche Export diese Zeile für Demo-Code
    start, ende = "DEMO-" + "START", "DEMO-" + "ENDE"
    ohne_demo = re.sub(rf"/\* {start} \*/.*?/\* {ende} \*/", "", ohne_variablen, flags=re.S)
    verstoesse = []
    for regel in re.finditer(r"([^{}]+)\{([^{}]*)\}", ohne_demo):
        selektor, inhalt = regel.group(1).strip(), regel.group(2)
        if selektor.startswith(".schema-"):
            continue
        for farbe in re.findall(r"#[0-9a-fA-F]{3,6}\b", inhalt):
            if farbe.lower() not in ("#fff", "#ffffff", "#000"):
                verstoesse.append(f"{selektor}: {farbe}")
    assert not verstoesse, verstoesse
