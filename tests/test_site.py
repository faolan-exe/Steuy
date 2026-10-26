"""Die Website (site/) ist die Seite, die Suchmaschinen sehen: Grundlagen prüfen."""

import json
import re
from pathlib import Path

import pytest

SITE = Path(__file__).parent.parent / "site"
INDEX = (SITE / "index.html").read_text(encoding="utf-8")


def test_titel_und_beschreibung_haben_eine_gute_laenge():
    titel = re.search(r"<title>(.*?)</title>", INDEX).group(1)
    beschreibung = re.search(r'<meta name="description" content="(.*?)">', INDEX).group(1)
    assert 30 <= len(titel) <= 65
    assert 100 <= len(beschreibung) <= 160


def test_wichtige_suchbegriffe_stehen_im_text():
    text = INDEX.lower()
    for begriff in (
        "kleinunternehmer",
        "kleingewerbe",
        "buchhaltungssoftware",
        "rechnungsprogramm",
        "rechnungswesen",
        "selbst gehostet",
        "quelloffen",
        "eür",
        "§ 19 ustg",
    ):
        assert begriff in text, begriff


def test_genau_eine_h1_und_canonical():
    assert INDEX.count("<h1") == 1
    assert 'rel="canonical"' in INDEX and 'property="og:image"' in INDEX


def test_strukturierte_daten_sind_gueltiges_json():
    bloecke = re.findall(r'<script type="application/ld\+json">(.*?)</script>', INDEX, re.S)
    typen = {json.loads(b)["@type"] for b in bloecke}
    assert {"SoftwareApplication", "FAQPage", "WebSite"} <= typen


def test_alle_bilder_haben_alt_text_und_existieren():
    for tag in re.findall(r"<img [^>]*>", INDEX):
        assert 'alt="' in tag
        quelle = re.search(r'src="(img/[^"]+)"', tag)
        if quelle:
            assert (SITE / quelle.group(1)).is_file(), quelle.group(1)
    assert (SITE / "img" / "og-bild.png").is_file()


def test_keine_fremden_ressourcen_und_keine_cookies():
    # Datenschutzseite verspricht: nichts von fremden Servern laden
    for tag in re.findall(r"<(?:script|link|img|iframe)[^>]*>", INDEX):
        for adresse in re.findall(r'(?:src|href)="(https?://[^"]+)"', tag):
            assert 'rel="canonical"' in tag or "stylesheet" not in tag, adresse
            assert "<script" not in tag or "src=" not in tag
    assert "document.cookie" not in INDEX


@pytest.mark.parametrize("seite", ["impressum.html", "datenschutz.html"])
def test_rechtsseiten_sind_noindex_und_verlinkt(seite):
    assert seite in INDEX
    assert "noindex" in (SITE / seite).read_text(encoding="utf-8")


def test_sitemap_und_robots_zeigen_auf_die_startseite():
    sitemap = (SITE / "sitemap.xml").read_text()
    assert "<loc>https://faolan-exe.github.io/Steuy/</loc>" in sitemap
    assert (
        "Sitemap: https://faolan-exe.github.io/Steuy/sitemap.xml"
        in (SITE / "robots.txt").read_text()
    )


def test_readme_hat_ueberschrift_und_verweist_auf_die_website():
    readme = (SITE.parent / "README.md").read_text(encoding="utf-8")
    assert "<h1>" in readme and "Buchhaltungssoftware für Kleinunternehmer" in readme
    assert "faolan-exe.github.io/Steuy" in readme
    assert (SITE.parent / "docs" / "faq.md").is_file()
