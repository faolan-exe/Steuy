"""Umrechnung zwischen Euro-Text und Integer-Cent (ADR 0001).

Beträge sind im ganzen Programm `int` in Cent. Nur hier wird Text gelesen oder erzeugt.
"""

import re

_TAUSENDER_PUNKT = re.compile(r"^\d{1,3}(\.\d{3})+$")
_TAUSENDER_KOMMA = re.compile(r"^\d{1,3}(,\d{3})+$")
_GANZZAHL = re.compile(r"^\d*$")


class GeldFormatFehler(ValueError):
    """Der Text ist kein eindeutiger Euro-Betrag."""


def euro_zu_cent(text: str) -> int:
    """Liest einen Euro-Betrag wie „1.234,56 €“ oder „12.5“ und gibt Cent zurück.

    Erlaubt sind Komma oder Punkt als Dezimaltrenner mit höchstens zwei Nachkommastellen,
    Tausenderpunkte (bzw. Tausenderkommas bei Dezimalpunkt) in Dreiergruppen, ein Vorzeichen
    und „€“ bzw. „EUR“. Alles Mehrdeutige wird abgelehnt.
    """
    if not isinstance(text, str):
        raise TypeError("Geldbeträge werden nur aus Text gelesen.")

    roh = text.strip().replace("−", "-")
    roh = re.sub(r"(€|EUR)$", "", roh).strip()
    roh = re.sub(r"^(€|EUR)", "", roh).strip()

    vorzeichen = 1
    if roh and roh[0] in "+-":
        vorzeichen = -1 if roh[0] == "-" else 1
        roh = roh[1:].strip()

    if not roh or roh in {",", "."}:
        raise GeldFormatFehler(f"Kein Betrag: {text!r}")

    euro_teil, cent_teil = _zerlege(roh, text)
    if not _GANZZAHL.match(euro_teil) or not _GANZZAHL.match(cent_teil) or len(cent_teil) > 2:
        raise GeldFormatFehler(f"Ungültiger Betrag: {text!r}")

    euro = int(euro_teil or "0")
    cent = int(cent_teil.ljust(2, "0"))
    return vorzeichen * (euro * 100 + cent)


def _zerlege(roh: str, original: str) -> tuple[str, str]:
    """Trennt in Euro- und Cent-Ziffern, Tausendertrenner bereits entfernt."""
    hat_komma = "," in roh
    hat_punkt = "." in roh

    if hat_komma and hat_punkt:
        dezimal = "," if roh.rfind(",") > roh.rfind(".") else "."
        tausender = "." if dezimal == "," else ","
        vorne, _, hinten = roh.rpartition(dezimal)
        muster = _TAUSENDER_PUNKT if tausender == "." else _TAUSENDER_KOMMA
        if not muster.match(vorne):
            raise GeldFormatFehler(f"Ungültige Tausendertrennung: {original!r}")
        return vorne.replace(tausender, ""), hinten

    trenner = "," if hat_komma else "." if hat_punkt else ""
    if not trenner:
        return roh, ""

    teile = roh.split(trenner)
    if len(teile) == 2 and len(teile[1]) <= 2:
        return teile[0], teile[1]
    if trenner == "." and _TAUSENDER_PUNKT.match(roh):
        return roh.replace(".", ""), ""
    raise GeldFormatFehler(f"Mehrdeutiger Betrag: {original!r}")


def _pruefe_cent(cent: int) -> None:
    if not isinstance(cent, int) or isinstance(cent, bool):
        raise TypeError("Geldbeträge sind immer int in Cent.")


def cent_zu_euro(cent: int) -> str:
    """Anzeige im deutschen Format: 123456 → „1.234,56 €“."""
    _pruefe_cent(cent)
    vorzeichen = "-" if cent < 0 else ""
    euro, rest = divmod(abs(cent), 100)
    return f"{vorzeichen}{euro:,}".replace(",", ".") + f",{rest:02d} €"


def cent_zu_dezimal(cent: int) -> str:
    """Maschinenformat mit Punkt und zwei Stellen: 123456 → „1234.56“ (CSV, QR-Code, APIs)."""
    _pruefe_cent(cent)
    vorzeichen = "-" if cent < 0 else ""
    euro, rest = divmod(abs(cent), 100)
    return f"{vorzeichen}{euro}.{rest:02d}"
