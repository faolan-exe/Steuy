"""Amtliche Prüfregeln für E-Rechnungen (Schematron, als XSLT übersetzt).

- EN 16931 (CII) vom CEN, Version 1.3.17, Lizenz EUPL 1.2 (LICENSE-en16931)
- XRechnung 3.0.2 der KoSIT, Schematron 2.6.0, Lizenz Apache 2.0 (LICENSE-xrechnung-schematron)

Dieselben Regeln nutzt das KoSIT-Prüftool. steuy prüft damit jede E-Rechnung vor dem
Festschreiben, eine fehlerhafte E-Rechnung verlässt das Programm also nicht.

Die Prüfung läuft standardmäßig in einem eigenen, kurzlebigen Prozess: Saxon belegt rund
200 MB Arbeitsspeicher, die danach sofort wieder frei sind (wichtig auf kleinen Thin Clients).
Mit ERECHNUNG_PRUEFUNG=intern bleibt Saxon im Webprozess geladen (schneller, mehr Speicher).
"""

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from lxml import etree

ORDNER = Path(__file__).parent
REGELN_EN16931 = ORDNER / "EN16931-CII-validation.xslt"
REGELN_XRECHNUNG = ORDNER / "XRechnung-CII-validation.xsl"
SVRL = {"s": "http://purl.oclc.org/dsdl/svrl"}

_sperre = threading.Lock()


@dataclass(frozen=True)
class Meldung:
    regel: str
    text: str
    schwer: bool  # fatal/error: ungültig; warning/information: nur Hinweis

    def __str__(self) -> str:
        return f"{self.regel}: {self.text}"


@cache
def _prozessor():
    from saxonche import PySaxonProcessor

    return PySaxonProcessor(license=False)


@cache
def _regelwerk(pfad: Path):
    return _prozessor().new_xslt30_processor().compile_stylesheet(stylesheet_file=str(pfad))


def _anwenden(pfad: Path, xml: bytes) -> list[Meldung]:
    with _sperre:  # Saxon/C ist je Prozessor nicht für parallele Aufrufe gedacht
        dokument = _prozessor().parse_xml(xml_text=xml.decode("utf-8"))
        ergebnis = _regelwerk(pfad).transform_to_string(xdm_node=dokument)
    bericht = etree.fromstring(ergebnis.encode("utf-8"))
    meldungen = []
    for treffer in bericht.findall(".//s:failed-assert", SVRL) + bericht.findall(
        ".//s:successful-report", SVRL
    ):
        flagge = (treffer.get("flag") or "fatal").lower()
        text = " ".join((treffer.findtext("s:text", namespaces=SVRL) or "").split())
        regel = treffer.get("id") or "?"
        # Der Text beginnt oft mit "[BR-XX]-", die Regel steht schon davor
        if text.startswith(f"[{regel}]"):
            text = text[len(regel) + 2 :].lstrip("- ")
        meldungen.append(Meldung(regel, text, flagge in ("fatal", "error")))
    return meldungen


class PruefungFehlgeschlagen(RuntimeError):
    pass


def pruefe_hier(xml: bytes, xrechnung: bool = False) -> list[Meldung]:
    """Im eigenen Prozess prüfen (lädt Saxon dauerhaft)."""
    meldungen = _anwenden(REGELN_EN16931, xml)
    if xrechnung:
        meldungen += _anwenden(REGELN_XRECHNUNG, xml)
    return meldungen


def pruefe_im_prozess(xml: bytes, xrechnung: bool = False) -> list[Meldung]:
    """In einem eigenen Python-Prozess prüfen, der danach endet und den Speicher freigibt."""
    wurzel = ORDNER.parents[2]
    umgebung = {**os.environ, "PYTHONPATH": str(wurzel)}
    try:
        lauf = subprocess.run(
            [sys.executable, "-m", "app.domain.erechnung_regeln", "x" if xrechnung else "e"],
            input=xml,
            capture_output=True,
            timeout=120,
            cwd=wurzel,
            env=umgebung,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as fehler:
        raise PruefungFehlgeschlagen(f"Prüfung nicht möglich: {fehler}") from fehler
    if lauf.returncode != 0:
        letzte = (lauf.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
        raise PruefungFehlgeschlagen(f"Prüfung nicht möglich: {' '.join(letzte)}")
    return [Meldung(**m) for m in json.loads(lauf.stdout)]


def pruefe_regeln(xml: bytes, xrechnung: bool = False) -> list[Meldung]:
    """Alle Meldungen nach EN 16931, bei einer XRechnung zusätzlich nach XRechnung 3.0."""
    if os.environ.get("ERECHNUNG_PRUEFUNG", "prozess") == "intern":
        return pruefe_hier(xml, xrechnung)
    return pruefe_im_prozess(xml, xrechnung)
